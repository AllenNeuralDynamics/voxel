import logging

class AxesMapping:

	def __init__(self):

		self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
		self.axis_map = dict()