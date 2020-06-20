import logging
from _collections import deque
from tensorflow.keras.utils import Sequence
import numpy as np
from h5py import File as H5File

logger = logging.getLogger('LSTM-based Model')


class GroupInfo:
    def __init__(self):
        self.path = ''
        self.clean_shape = None
        self.dirty_shape = None
        self.n_fft = 0
        self.attributes = dict()


class DataGenerator(Sequence):
    """Generates data for Keras"""
    def __init__(self, h5_file_path, batch_size=32, shuffle=True, fft_size=0, n_time_steps=1, n_batches=0):
        self.batch_size = batch_size
        self.h5_file_path = h5_file_path
        self.shuffle = shuffle
        self.fft_size = fft_size
        self.n_time_steps = n_time_steps
        self.n_batches = n_batches
        self.h5_info = None
        self.groups = []
        self.n_fft = 0
        self.group_idx = 0
        self.target_group = None
        self.fft_idx = 0
        self.batch = deque(maxlen=n_time_steps)

        self.__startup()
        self.on_epoch_end()

    def __startup(self):
        with H5File(self.h5_file_path, 'r') as f:
            for main_group_key in f.keys():
                main_group = f[main_group_key]
                for group_key in main_group.keys():
                    group = main_group[group_key]
                    self.__parse_group_info(group)
                    if self.n_batches != 0 and (self.n_fft/self.batch_size) >= self.n_batches:
                        break

        self.target_group = self.groups[0]

    def __parse_group_info(self, h5_group):
        group_info = GroupInfo()
        group_info.path = h5_group.name
        group_info.clean_shape = h5_group['CLEAN/DB'].shape
        group_info.dirty_shape = h5_group['DIRTY/DB'].shape
        for key in h5_group.attrs.keys():
            group_info.attributes[key] = h5_group.attrs[key]
        if group_info.clean_shape == group_info.dirty_shape:
            logger.info('Found %d FFTs in %s' % (group_info.clean_shape[0], group_info.path))
            group_info.n_fft = group_info.clean_shape[0]
            self.n_fft += group_info.n_fft
            self.groups.append(group_info)
        else:
            logger.info('Number of FFTs mismatch\n\tClean %d\n\tDirty %d' %
                        (group_info.clean_shape[0], group_info.dirty_shape[0]))

    def __increment_target_group(self):
        self.group_idx += 1
        self.target_group = self.groups[self.group_idx]
        self.fft_idx = 0

    def __len__(self):
        """Denotes the number of batches per epoch"""
        n_batches = int(np.floor((self.n_fft - self.n_time_steps + 1) / self.batch_size))
        #logger.debug('Number of batches %d' % n_batches)
        return n_batches

    def __getitem__(self, index):
        """Generate one batch of data"""

        # Generate data
        X, Y = self.__data_generation()

        return X, Y

    def on_epoch_end(self):
        'Updates indexes after each epoch'
        pass

    def __data_generation(self):
        """Generates data containing in batch_size"""
        X = np.empty((self.batch_size, self.n_time_steps, self.fft_size), dtype=np.float64)
        Y = np.empty((self.batch_size, self.fft_size), dtype=np.float64)

        # Generate data
        with H5File(self.h5_file_path, 'r') as f:
            for idx in range(self.batch_size):
                # Store sample
                if not self.batch:
                    for idx_time in range(self.n_time_steps - 1):
                        self.batch.append(f[self.target_group.path + '/DIRTY/DB'][self.fft_idx, :, :self.fft_size])
                        self.fft_idx += 1
                self.batch.append(f[self.target_group.path + '/DIRTY/DB'][self.fft_idx, :, :self.fft_size])
                X[idx, :, :] = self.batch
                Y[idx, :] = f[self.target_group.path + '/CLEAN/DB'][self.fft_idx, 0, :self.fft_size]
                self.fft_idx += 1
                if self.fft_idx >= self.target_group.n_fft:
                    self.__increment_target_group()

        return X, Y
