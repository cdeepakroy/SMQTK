SMQTK Pending Release Notes
===========================


Updates / New Features since v0.8.0
-----------------------------------


Fixes since v0.8.0
------------------

Descriptor Generator Plugins

* Fix issue with CaffeDescriptorGenerator where the GPU would not be
  appropriately used on a separate thread/process after initialization occurs on
  the main (or some other) thread.

Descriptor Index Plugins

* Fix bug in PostgreSQL plugin where the helper class was not being called
  appropriately.

Utilities

* Fix bug in PostgreSQL connection helper where the connection object was
  being called upon when it may not have been initialized.
