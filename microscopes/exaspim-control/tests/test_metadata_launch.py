""" testing metadata launch """

import unittest
from unittest.mock import MagicMock
from exaspim_control.metadata_launch import MetadataLaunch
from aind_data_schema.core import acquisition
import shutil
import os
from pathlib import Path

RESOURCES_DIR = (Path(os.path.dirname(os.path.realpath(__file__))))

class MetaDataLaunchTests(unittest.TestCase):
    """tests for MetaDataLaunch"""

    def test_writing(self):
        """Test ability to write acquisition json"""
        instrument_config = {'instrument':
                                 {'channels':
                                      {'CH639':
                                           {'filters': ['BP639'],
                                            'lasers': ['639 nm'],
                                            'cameras': ['vp-151mx']}
                                       }
                                  }
                             }
        mocked_laser = MagicMock()
        mocked_laser.configure_mock(wavelength=639)
        mocked_instrument = MagicMock(lasers={'639 nm': mocked_laser}, config=instrument_config)

        mocked_metadata = MagicMock()
        mocked_metadata.configure_mock(experimenter_full_name=['Chris P. Bacon'],
                                       subject_id=123,
                                       instrument_id='exaspim123',
                                       chamber_immersion={'medium': 'oil',
                                                          'refractive_index': 1.33},
                                       x_anatomical_direction='Anterior to Posterior',
                                       y_anatomical_direction='Inferior to Superior',
                                       z_anatomical_direction='Left to Right')
        acquisition_config = {'acquisition':
            {'tiles':
                [
                    {'channel': 'CH639',
                     'position_mm':
                         {'x': -4.537907199999999,
                          'y': 11.601536,
                          'z': 12.0},
                     'tile_number': 0,
                     'vp-151mx':
                         {'binning': 1},
                     '639 nm': {
                         'power_setpoint_mw': 0.0},
                     'steps': 0,
                     'step_size': 0.0,
                     'prefix': 'tile'}
                ]
            }
        }
        mocked_acquisition = MagicMock()
        mocked_acquisition.configure_mock(metadata=mocked_metadata, config=acquisition_config)

        mock_signal = MagicMock()
        mock_signal.configure_mock(connect=lambda x: None)
        mocked_acquisition_view = MagicMock()
        mocked_acquisition_view.configure_mock(acquisitionStarted=mock_signal, acquisitionEnded=mock_signal)

        metadata_launch = MetadataLaunch(instrument=mocked_instrument,
                                         acquisition=mocked_acquisition,
                                         instrument_view=MagicMock(),
                                         acquisition_view=mocked_acquisition_view)
        metadata_launch.acquisition_start_time = '2022-12-27 08:26:49.219717'
        metadata_launch.acquisition_end_time = '2022-12-27 08:26:49.219717'
        actual_schema = metadata_launch.parse_metadata('', '')
        expected_schema = acquisition.Acquisition(**{'experimenter_full_name': ['Chris P. Bacon'],
                                                     'specimen_id': '123',
                                                     'subject_id': '123',
                                                     'instrument_id': 'exaspim123',
                                                     'session_start_time': '2022-12-27 08:26:49.219717',
                                                     'session_end_time': '2022-12-27 08:26:49.219717',
                                                     'local_storage_directory': '',
                                                     'external_storage_directory': '',
                                                     'chamber_immersion': {'medium': 'oil',
                                                                           'refractive_index': 1.33},
                                                     'axes': [
                                                         {
                                                             'name': 'X',
                                                             'dimension': 2,
                                                             'direction': 'Anterior_to_posterior'
                                                         },
                                                         {
                                                             'name': 'Y',
                                                             'dimension': 1,
                                                             'direction': 'Inferior_to_superior'
                                                         },
                                                         {
                                                             'name': 'Z',
                                                             'dimension': 0,
                                                             'direction': 'Left_to_right'
                                                         }
                                                     ],
                                                     'tiles': [{
                                                         'file_name': f"tile_000000_ch_CH639_camera_vp-151mx",
                                                         'coordinate_transformations': [
                                                             {
                                                                 "type": "scale",
                                                                 "scale": [
                                                                     "0.748",
                                                                     "0.748",
                                                                     "1"
                                                                 ]
                                                             },
                                                             {
                                                                 "type": "translation",
                                                                 "translation": [
                                                                     "0",
                                                                     "0",
                                                                     "0"
                                                                 ]
                                                             }
                                                         ],
                                                         'channel': {
                                                             'channel_name': 'CH639',
                                                             "light_source_name": '639 nm',
                                                             "filter_names": ['BP639'],
                                                             "detector_name": 'vp-151mx',
                                                             "additional_device_names": ['BP639'],
                                                             "excitation_wavelength": 639,
                                                             "excitation_power": 0,
                                                             "filter_wheel_index": 0
                                                         }

                                                     }

                                                     ]
                                                     })
        self.assertEqual(expected_schema, actual_schema)

    def test_saving(self):
        """Test ability to write and save acquisition json"""
        # TODO: if unit tests ever get automated by github this one will prob fail because it writes and deletes files
        instrument_config = {'instrument':
                                 {'channels':
                                      {'CH639':
                                           {'filters': ['BP639'],
                                            'lasers': ['639 nm'],
                                            'cameras': ['vp-151mx']}
                                       }
                                  }
                             }
        mocked_laser = MagicMock()
        mocked_laser.configure_mock(wavelength=639)
        mocked_instrument = MagicMock(lasers={'639 nm': mocked_laser}, config=instrument_config)

        mocked_metadata = MagicMock()
        mocked_metadata.configure_mock(experimenter_full_name=['Chris P. Bacon'],
                                       subject_id=123,
                                       instrument_id='exaspim123',
                                       chamber_immersion={'medium': 'oil',
                                                          'refractive_index': 1.33},
                                       x_anatomical_direction='Anterior to Posterior',
                                       y_anatomical_direction='Inferior to Superior',
                                       z_anatomical_direction='Left to Right')
        acquisition_config = {'acquisition':
            {'tiles':
                [
                    {'channel': 'CH639',
                     'position_mm':
                         {'x': -4.537907199999999,
                          'y': 11.601536,
                          'z': 12.0},
                     'tile_number': 0,
                     'vp-151mx':
                         {'binning': 1},
                     '639 nm': {
                         'power_setpoint_mw': 0.0},
                     'steps': 0,
                     'step_size': 0.0,
                     'prefix': 'tile'}
                ]
            }
        }
        # Create temporary dummy folders
        os.makedirs(RESOURCES_DIR / 'external_test/test', exist_ok=True)
        os.makedirs(RESOURCES_DIR / 'external_test1/test', exist_ok=True)
        os.makedirs(RESOURCES_DIR / 'local_test/test', exist_ok=True)
        os.makedirs(RESOURCES_DIR / 'local_test1/test', exist_ok=True)

        mocked_transfer = MagicMock()
        mocked_transfer.configure_mock(external_path=RESOURCES_DIR / 'external_test',
                                       acquisition_name='test')

        mocked_transfer1 = MagicMock()
        mocked_transfer1.configure_mock(external_path=RESOURCES_DIR / 'external_test1',
                                        acquisition_name='test')

        mocked_writer = MagicMock()
        mocked_writer.configure_mock(local_path=RESOURCES_DIR / 'local_test',
                                     acquisition_name='test')

        mocked_writer1 = MagicMock()
        mocked_writer1.configure_mock(local_path=RESOURCES_DIR / 'local_test1',
                                      acquisition_name='test')
        try:
            # test one transfer
            mocked_acquisition = MagicMock()
            mocked_acquisition.configure_mock(metadata=mocked_metadata,
                                              config=acquisition_config,
                                              transfers={'vp-151mx': {'test': mocked_transfer}})

            mock_signal = MagicMock()
            mock_signal.configure_mock(connect=lambda x: None)
            mocked_acquisition_view = MagicMock()
            mocked_acquisition_view.configure_mock(acquisitionStarted=mock_signal, acquisitionEnded=mock_signal)

            metadata_launch = MetadataLaunch(instrument=mocked_instrument,
                                             acquisition=mocked_acquisition,
                                             instrument_view=MagicMock(),
                                             acquisition_view=mocked_acquisition_view)
            metadata_launch.acquisition_start_time = '2022-12-27 08:26:49.219717'
            metadata_launch.acquisition_end_time = '2022-12-27 08:26:49.219717'

            metadata_launch.create_acquisition_json()
            self.assertTrue(os.path.exists(RESOURCES_DIR / 'external_test/test/exaspim_acquisition.json'))

            # test multiple transfers
            mocked_acquisition = MagicMock()
            mocked_acquisition.configure_mock(metadata=mocked_metadata,
                                              config=acquisition_config,
                                              transfers={'vp-151mx': {'test': mocked_transfer,
                                                                      'test1':mocked_transfer1}})

            mock_signal = MagicMock()
            mock_signal.configure_mock(connect=lambda x: None)
            mocked_acquisition_view = MagicMock()
            mocked_acquisition_view.configure_mock(acquisitionStarted=mock_signal, acquisitionEnded=mock_signal)

            metadata_launch = MetadataLaunch(instrument=mocked_instrument,
                                             acquisition=mocked_acquisition,
                                             instrument_view=MagicMock(),
                                             acquisition_view=mocked_acquisition_view)
            metadata_launch.acquisition_start_time = '2022-12-27 08:26:49.219717'
            metadata_launch.acquisition_end_time = '2022-12-27 08:26:49.219717'

            metadata_launch.create_acquisition_json()
            self.assertTrue(os.path.exists(RESOURCES_DIR / 'external_test/test/exaspim_acquisition.json'))
            self.assertTrue(os.path.exists(RESOURCES_DIR / 'external_test1/test/exaspim_acquisition.json'))

            # test no transfer, one writer
            mocked_acquisition = MagicMock()
            mocked_acquisition.configure_mock(metadata=mocked_metadata,
                                              config=acquisition_config,
                                              transfers={},
                                              writers={'vp-151mx': {'test': mocked_writer}})

            mock_signal = MagicMock()
            mock_signal.configure_mock(connect=lambda x: None)
            mocked_acquisition_view = MagicMock()
            mocked_acquisition_view.configure_mock(acquisitionStarted=mock_signal, acquisitionEnded=mock_signal)

            metadata_launch = MetadataLaunch(instrument=mocked_instrument,
                                             acquisition=mocked_acquisition,
                                             instrument_view=MagicMock(),
                                             acquisition_view=mocked_acquisition_view)
            metadata_launch.acquisition_start_time = '2022-12-27 08:26:49.219717'
            metadata_launch.acquisition_end_time = '2022-12-27 08:26:49.219717'

            metadata_launch.create_acquisition_json()
            self.assertTrue(os.path.exists(RESOURCES_DIR / 'local_test/test/exaspim_acquisition.json'))

            # test not transfers, multiple writers
            mocked_acquisition = MagicMock()
            mocked_acquisition.configure_mock(metadata=mocked_metadata,
                                              config=acquisition_config,
                                              transfers={},
                                              writers={'vp-151mx': {'test': mocked_writer, 'test1': mocked_writer1}})

            mock_signal = MagicMock()
            mock_signal.configure_mock(connect=lambda x: None)
            mocked_acquisition_view = MagicMock()
            mocked_acquisition_view.configure_mock(acquisitionStarted=mock_signal, acquisitionEnded=mock_signal)

            metadata_launch = MetadataLaunch(instrument=mocked_instrument,
                                             acquisition=mocked_acquisition,
                                             instrument_view=MagicMock(),
                                             acquisition_view=mocked_acquisition_view)
            metadata_launch.acquisition_start_time = '2022-12-27 08:26:49.219717'
            metadata_launch.acquisition_end_time = '2022-12-27 08:26:49.219717'

            metadata_launch.create_acquisition_json()
            self.assertTrue(os.path.exists(RESOURCES_DIR / 'local_test/test/exaspim_acquisition.json'))
            self.assertTrue(os.path.exists(RESOURCES_DIR / 'local_test1/test/exaspim_acquisition.json'))

        finally:
            shutil.rmtree(RESOURCES_DIR / 'external_test')
            shutil.rmtree(RESOURCES_DIR / 'external_test1')
            shutil.rmtree(RESOURCES_DIR / 'local_test')
            shutil.rmtree(RESOURCES_DIR / 'local_test1')


if __name__ == "__main__":
    unittest.main()
