# -*- coding: utf-8 -*-
"""
LICENCE
-------
Copyright 2015 by Kitware, Inc. All Rights Reserved. Please refer to
KITWARE_LICENSE.TXT for licensing information, or contact General Counsel,
Kitware, Inc., 28 Corporate Drive, Clifton Park, NY 12065.

"""

import base64
import flask
import logging
import mimetypes
import multiprocessing
import os
import requests
import tempfile

from smqtk.utils import SimpleTimer
from smqtk.utils.configuration import ContentDescriptorConfiguration


MIMETYPES = mimetypes.MimeTypes()


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class DescriptorServiceServer (flask.Flask):
    """
    Simple server that takes in a specification of the following form:

        /<descriptor_type>/<uri>[?...]

    Computes the requested descriptor for the given file and returns that via
    a JSON structure.

    Standard return JSON:
    {
        "success": <bool>,
        "descriptor": [ <float>, ... ]
        "message": <string>,
        "reference_uri": <uri>
    }

    """

    # Optional environment variable that can point to a configuration file
    ENV_CONFIG = "DescriptorService_CONFIG"

    @property
    def log(self):
        return logging.getLogger('.'.join((self.__module__,
                                           self.__class__.__name__)))

    def __init__(self, config_filepath=None):
        super(DescriptorServiceServer, self).__init__(
            self.__class__.__name__,
            static_folder=os.path.join(SCRIPT_DIR, 'static'),
            template_folder=os.path.join(SCRIPT_DIR, 'templates')
        )

        #
        # Configuration setup
        #
        config_env_loaded = config_file_loaded = None

        # Load default -- This should always be present, aka base defaults
        self.config.from_object('smqtk_config')
        config_default_loaded = True

        # Load from env var if present
        if self.ENV_CONFIG in os.environ:
            self.log.info("Loading config from env var (%s)...",
                          self.ENV_CONFIG)
            self.config.from_envvar(self.ENV_CONFIG)
            config_env_loaded = True

        # Load from configuration file if given
        if config_filepath and os.path.isfile(config_filepath):
            config_file_path = os.path.expanduser(os.path.abspath(config_filepath))
            self.log.info("Loading config from file (%s)...", config_file_path)
            self.config.from_pyfile(config_file_path)
            config_file_loaded = True

        self.log.debug("Config defaults loaded : %s", config_default_loaded)
        self.log.debug("Config from env loaded : %s", config_env_loaded)
        self.log.debug("Config from file loaded: %s", config_file_loaded)
        if not (config_default_loaded or config_env_loaded or config_file_loaded):
            raise RuntimeError("No configuration file specified for loading. "
                               "(%s=%s) (file=%s)"
                               % (self.ENV_CONFIG,
                                  os.environ.get(self.ENV_CONFIG, None),
                                  config_filepath))

        # Cache of ContentDescriptor instances
        descriptor_cache = {}
        descriptor_cache_lock = multiprocessing.RLock()

        #
        # Security
        #
        self.secret_key = self.config['SECRET_KEY']

        @self.route("/")
        def list_ingest_labels():
            return flask.jsonify({
                "labels": sorted(ContentDescriptorConfiguration
                                 .available_labels())
            })

        @self.route("/<string:descriptor_label>/<path:uri>")
        def compute_descriptor(descriptor_label, uri):
            """
            # Data modes for upload/use
                - local filepath
                - base64
                - http/s URL

            The following sub-sections detail how different URI's can be used.

            ## Local Filepath
            The URI string must be prefixed with ``file://``, followed by the
            full path to the data file to describe.

            ## Base 64 data
            The URI string must be prefixed with "base64://", followed by the
            base64 encoded string. This mode also requires an additional
            ``?content_type=`` to provide data content type information. This
            mode saves the encoded data to temporary file for processing.

            ## HTTP/S address
            This is the default mode when the URI prefix is none of the above.
            This uses the requests module to locally download a data file
            for processing.

            """
            success = True
            message = "Nothing has happened yet"

            # Resolve URI
            filepath = None
            remove_file = False

            # TODO: Make this block construct a DataElement impl instance
            #       Requires the construction of MemoryElement and WebElement
            if uri[:7] == "file://":
                self.log.debug("Given local disk filepath")
                _filepath = uri[7:]
                if not os.path.isfile(_filepath):
                    success = False
                    message = "File URI did not point to an existing file on " \
                              "disk."
                else:
                    filepath = _filepath

            elif uri[:9] == "base64://":
                self.log.debug("Given base64 string")
                content_type = flask.request.args.get('content_type', None)
                self.log.debug("Content type: %s", content_type)
                if not content_type:
                    self.log.warning("No content-type with given base64 data")
                    success = False
                    message = "No content-type with given base64 content."
                else:
                    b64str = uri[9:]
                    ext = MIMETYPES.guess_extension(content_type)
                    fd, filepath = tempfile.mkstemp(suffix=ext)
                    os.close(fd)
                    self.log.debug("Saving image with type '%s' to: %s",
                                   ext, filepath)
                    with open(filepath, 'wb') as ofile:
                        ofile.write(base64.decodestring(b64str))
                    self.log.debug("Image file written.")
                    remove_file = True

            else:
                self.log.debug("Given URL")
                r = requests.get(uri)
                if r.ok:
                    ext = MIMETYPES.guess_extension(r.headers['content-type'])
                    fd, filepath = tempfile.mkstemp(suffix=ext)
                    os.close(fd)
                    self.log.debug("Saving image with type '%s' to: %s",
                                   ext, filepath)
                    with open(filepath, 'wb') as ofile:
                        ofile.write(r.content)
                    self.log.debug("Image file written.")
                    remove_file = True
                else:
                    self.log.debug("Request failed")
                    success = False
                    message = "Web request did not yield an OK response " \
                              "(received %d :: %s)" \
                              % (r.status_code, r.reason)

            descriptor = None
            if filepath:
                from smqtk.data_rep import get_data_element_impls
                de = get_data_element_impls()['FileElement'](filepath)

                # Get the descriptor instance for the given label, creating it
                # if necessary.
                if descriptor_label not in descriptor_cache:
                    self.log.debug("Creating descriptor '%s'", descriptor_label)
                    with descriptor_cache_lock:
                        descriptor_cache[descriptor_label] = \
                            ContentDescriptorConfiguration\
                            .new_inst(descriptor_label)
                with descriptor_cache_lock:
                    #: :type: smqtk.content_description.ContentDescriptor
                    d = descriptor_cache[descriptor_label]
                with SimpleTimer("Computing descriptor...", self.log.debug):
                    descriptor = d.compute_descriptor(de)
                    message = "Descriptor computed of type '%s'" \
                              % descriptor_label

                if remove_file:
                    self.log.debug("Removing downloaded file.")
                    os.remove(filepath)

            return flask.jsonify({
                "success": success,
                "message": message,
                "descriptor": descriptor.tolist(),
                "reference_uri": uri
            })

    def run(self, host=None, port=None, debug=False, **options):
        """
        Override of the run method, drawing running host and port from
        configuration by default. 'host' and 'port' values specified as argument
        or keyword will override the app configuration.
        """
        super(DescriptorServiceServer, self)\
            .run(host=(host or self.config['RUN_HOST']),
                 port=(port or self.config['RUN_PORT']),
                 **options)
