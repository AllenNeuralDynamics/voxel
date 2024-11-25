from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os
from configparser import ConfigParser

import six

logger = logging.getLogger(__name__)


if six.PY2:
    import StringIO as io
else:
    import io
    from itertools import chain


class MyConfigParser(ConfigParser):
    def __init__(self, fName=None, defaults={}, create_file=True):
        ConfigParser.__init__(self, defaults)
        self.dummySection = "dummy"
        if fName:
            # create file if not existing

            if create_file and not os.path.exists(fName):
                try:
                    logger.debug("trying to create %s" % fName)
                    with open(fName, "w"):
                        pass
                except Exception as e:
                    logger.debug("failed to create %s" % fName)
                    logger.debug(e)

            self.read(fName)

    def read(self, fName):
        try:
            with open(fName) as f:
                if six.PY2:
                    f = io.StringIO("[%s]\n%s" % (self.dummySection, f.read()))
                    self.readfp(f)
                else:
                    f = chain(("[%s]" % self.dummySection,), f)
                    self.read_file(f)

        except Exception as e:
            logger.warn(e)

    def get(self, key, defaultValue=None, **kwargs):
        try:
            val = ConfigParser.get(self, self.dummySection, key, **kwargs)
            logger.debug("from config file: %s = %s " % (key, val))
            return val
        except Exception as e:
            logger.debug("%s (%s)" % (e, key))
            return defaultValue


if __name__ == "__main__":
    c = MyConfigParser()
