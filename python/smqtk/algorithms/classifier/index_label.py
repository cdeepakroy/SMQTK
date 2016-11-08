from smqtk.algorithms import Classifier
from smqtk.representation.data_element import from_uri


class IndexLabelClassifier (Classifier):
    """
    Applies a listing of labels (new-line separated) to input "descriptor"
    values, which is actually a vector of class confidence values.
    """

    @classmethod
    def is_usable(cls):
        return True

    def __init__(self, index_to_label_uri):
        super(IndexLabelClassifier, self).__init__()

        # load label vector
        self.index_to_label_uri = index_to_label_uri
        self.label_vector = [l.strip() for l in
                             from_uri(index_to_label_uri).to_buffered_reader()]

    def get_config(self):
        return {
            "index_to_label_uri": self.index_to_label_uri,
        }

    def get_labels(self):
        """
        Get the sequence of class labels that this classifier can classify
        descriptors into. This includes the negative label.

        :return: Sequence of possible classifier labels.
        :rtype: collections.Sequence[collections.Hashable]

        :raises RuntimeError: No model loaded.

        """
        # copying container
        return list(self.label_vector)

    def _classify(self, d):
        """
        Internal method that defines the generation of the classification map
        for a given DescriptorElement. This returns a dictionary mapping
        integer labels to a floating point value.

        :param d: DescriptorElement containing the vector to classify.
        :type d: smqtk.representation.DescriptorElement

        :raises RuntimeError: Could not perform classification for some reason
            (see message).

        :return: Dictionary mapping trained labels to classification confidence
            values
        :rtype: dict[collections.Hashable, float]

        """
        return dict(zip(self.label_vector, d.vector()))
