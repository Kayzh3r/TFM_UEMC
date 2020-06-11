import logging
import os
import numpy as np
from argparse import ArgumentParser
from scipy.signal import decimate, spectrogram, get_window
from librosa.core import amplitude_to_db
from pydub import AudioSegment, effects
from h5py import File
from src.errors import ResamplingError
from src.DBManager import DBManager
from src.AudioBooksManager import AudioBooksManager
from src.NoiseManager import NoiseManager

logger = logging.getLogger('DataConverter')


class DataManager:
    def __init__(self):
        self.__INPUT_SAMPLING_RATE = int(11025)
        self.__N_SAMPLES_WINDOW = int(1024)
        self.__N_SAMPLES_OVERLAP = int(0.5*self.__N_SAMPLES_WINDOW)
        self.__WINDOW = 'hann'
        self.__CHROME_DRIVER_PATH = r"resources/chromedriver"

        self.__db = DBManager()
        self.__audio_manager = AudioBooksManager(self.__db, self.__CHROME_DRIVER_PATH)
        self.__noise_manager = NoiseManager(self.__db)

    def main(self, filename='', mode='', download=0, noises=[], limit=0):
        try:
            if download:
                logging.info('Downloading audio books for training model')
                self.__audio_manager.downloadData()
                logging.info('Downloading noise audios for training model')
                self.__noise_manager.downloadData()
            logging.info('Retrieving audio-noise combinations')
            file_combinations = self.__db.modelTrainGetCombination(self.__INPUT_SAMPLING_RATE, noises, limit)
            with File(filename, mode) as f:
                logging.info('Creating group for SPS:%d and FFT:%d' % (self.__INPUT_SAMPLING_RATE,
                                                                       self.__N_SAMPLES_WINDOW))
                main_group = f.create_group(np.string_('SPS%dFFT%d' % (self.__INPUT_SAMPLING_RATE,
                                                                       self.__N_SAMPLES_WINDOW)))
                main_group.attrs.create(np.string_('SAMPLE_RATE'), np.string_(self.__INPUT_SAMPLING_RATE))
                main_group.attrs.create(np.string_('FFT_SIZE'), np.string_(self.__N_SAMPLES_WINDOW))
                for idx, file_combination in enumerate(file_combinations):
                    try:
                        logging.info('Loading data')
                        clean_info = self.__db.audioBookGetById(file_combination[1])
                        clean = self.load_audio(clean_info[0][9], normalized=False)
                        if idx > 0:
                            if file_combination[2] != file_combinations[idx - 1][2]:
                                noise_info = self.__db.noiseGetById(file_combination[2])
                                noise = self.load_audio(noise_info[0][3], normalized=False)
                        else:
                            noise_info = self.__db.noiseGetById(file_combination[2])
                            noise = self.load_audio(noise_info[0][3], normalized=False)

                        if clean.duration_seconds > noise.duration_seconds:
                            logging.info('Clipping clean audio to fit noise audio duration')
                            clean = clean[:noise.duration_seconds]

                        logging.info('Overlaying noise and clean audios')
                        dirty = clean.overlay(noise)
                        clean_samples = np.array(clean.get_array_of_samples(), dtype=np.float32)
                        clean_sampling_rate = clean.frame_rate
                        dirty_samples = np.array(dirty.get_array_of_samples(), dtype=np.float32)
                        dirty_sampling_rate = dirty.frame_rate
                        logging.info('Processing data')
                        dirty_freq, dirty_time, dirty_db, dirty_phase = self.__prepateInput(dirty_samples,
                                                                                            dirty_sampling_rate)
                        clean_freq, clean_time, clean_db, clean_phase = self.__prepateInput(clean_samples,
                                                                                            clean_sampling_rate)
                        logging.info('Storing data')
                        self.__store_h5_data(main_group, file_combination, clean_info[0], noise_info[0],
                                             clean_freq, clean_time, clean_db, clean_phase,
                                             dirty_freq, dirty_time, dirty_db, dirty_phase)
                    except ResamplingError as e:
                        logging.warning(str(e), exc_info=True)

        except Exception as e:
            logging.error(str(e), exc_info=True)
            raise

    def __resample(self, input_signal, input_sampling_rate):
        if input_sampling_rate % self.__INPUT_SAMPLING_RATE:
            raise ResamplingError('Downsampling factor is not integer number\n'
                                  '\tInput sampling rate: %d\n' % input_sampling_rate +
                                  '\tTarget sampling rate: %d\n' % self.__INPUT_SAMPLING_RATE)
        factor = input_sampling_rate / self.__INPUT_SAMPLING_RATE
        logger.info('Input sampling rate is different from the expected by the model.\n' +
                    '\rInput sampling rate: ' + str(input_sampling_rate) + '\n' +
                    '\rModel sampling rate: ' + str(self.__INPUT_SAMPLING_RATE) + '\n' +
                    'Resampling input signal by factor: ' + str(factor))
        in_signal = decimate(input_signal, int(factor))
        return in_signal

    def __prepateInput(self, input_signal, sampling_rate):
        if sampling_rate != self.__INPUT_SAMPLING_RATE:
            input_signal = self.__resample(input_signal, sampling_rate)
        freq, time, stft = spectrogram(
            input_signal, fs=self.__INPUT_SAMPLING_RATE,
            window=get_window(self.__WINDOW, self.__N_SAMPLES_WINDOW),
            # nperseg=None,
            noverlap=self.__N_SAMPLES_OVERLAP, nfft=self.__N_SAMPLES_WINDOW,
            # detrend='constant',
            return_onesided=True, scaling='spectrum', axis=-1, mode='complex')
        db_values = amplitude_to_db(np.abs(stft))
        db_values = np.transpose(db_values)[:, np.newaxis, :]
        phase = np.angle(stft)
        return [freq, time, db_values, phase]

    def __store_h5_data(self, main_group, file_combination, clean_info, noise_info,
                        clean_freq, clean_time, clean_db, clean_phase,
                        dirty_freq, dirty_time, dirty_db, dirty_phase):
        combination_group = main_group.create_group(np.string_('COMBINATION@ID_%d' % file_combination[0]))
        combination_group.attrs.create(np.string_('COMBINATION@ID'), np.int32(file_combination[0]))
        combination_group.attrs.create(np.string_('COMBINATION@SAMPLE_RATE'), np.float64(self.__INPUT_SAMPLING_RATE))
        combination_group.attrs.create(np.string_('CLEAN@ID'), np.int32(clean_info[0]))
        combination_group.attrs.create(np.string_('CLEAN@BOOK_DUMMY_NAME'), np.string_(clean_info[1]))
        combination_group.attrs.create(np.string_('CLEAN@BOOK_NAME'), clean_info[2])
        combination_group.attrs.create(np.string_('CLEAN@BOOK_AUTHOR'), clean_info[3])
        combination_group.attrs.create(np.string_('CLEAN@BOOK_URL'), np.string_(clean_info[4]))
        combination_group.attrs.create(np.string_('CLEAN@BOOK_LANGUAGE'), clean_info[5])
        combination_group.attrs.create(np.string_('CLEAN@BOOK_N_TRACK'), np.int32(clean_info[7]))
        combination_group.attrs.create(np.string_('CLEAN@TRACK_NAME'), np.string_(clean_info[8]))
        combination_group.attrs.create(np.string_('CLEAN@TRACK_SAMPLE_RATE'), np.float64(clean_info[11]))
        combination_group.attrs.create(np.string_('NOISE@ID'), np.int32(noise_info[0]))
        combination_group.attrs.create(np.string_('NOISE@NAME'), noise_info[1])
        combination_group.attrs.create(np.string_('NOISE@URL'), np.string_(noise_info[2]))
        combination_group.attrs.create(np.string_('NOISE@ORIGINAL_N_CHANNEL'), np.int8(noise_info[4]))
        combination_group.attrs.create(np.string_('NOISE@ORIGINAL_SAMPLE_RATE'), np.float64(noise_info[5]))
        clean_group = combination_group.create_group(r'CLEAN')
        clean_group.create_dataset('FREQ', data=clean_freq)
        clean_group.create_dataset('TIME', data=clean_time)
        clean_group.create_dataset('DB', data=clean_db)
        clean_group.create_dataset('PHASE', data=clean_phase)
        clean_group.attrs.create(np.string_('FFT@SIZE'), np.int32(self.__N_SAMPLES_WINDOW))
        clean_group.attrs.create(np.string_('FFT@N_SAMPLES_OVERLAP'), np.int32(self.__N_SAMPLES_OVERLAP))
        clean_group.attrs.create(np.string_('FFT@WINDOW'), np.string_(self.__WINDOW))
        dirty_group = combination_group.create_group(r'DIRTY')
        dirty_group.create_dataset('FREQ', data=dirty_freq)
        dirty_group.create_dataset('TIME', data=dirty_time)
        dirty_group.create_dataset('DB', data=dirty_db)
        dirty_group.create_dataset('PHASE', data=dirty_phase)
        dirty_group.attrs.create(np.string_('FFT@SIZE'), np.int32(self.__N_SAMPLES_WINDOW))
        dirty_group.attrs.create(np.string_('FFT@N_SAMPLES_OVERLAP'), np.int32(self.__N_SAMPLES_OVERLAP))
        dirty_group.attrs.create(np.string_('FFT@WINDOW'), np.string_(self.__WINDOW))

    @staticmethod
    def load_audio(path, normalized=True):
        ext = os.path.splitext(path)[1][1:]
        logging.info('Loading audio ' + path + ' with file type ' + ext)
        rawSound = AudioSegment.from_file(path, ext)
        if rawSound.channels != 1:
            logging.info('Audio contains more than one channel. Setting to single channel')
            rawSound = rawSound.set_channels(1)
        if normalized:
            logging.info('Normalize audio')
            return effects.normalize(rawSound)
        else:
            return rawSound


if __name__ == "__main__":
    try:
        # set up logging to file
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(name)-20s %(levelname)-8s %(message)s',
                            datefmt='%m-%d %H:%M',
                            filename='./DataConverter.log',
                            filemode='w+')
        # define a Handler which writes DEBUG messages or higher to the sys.stderr
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        # set a format which is simpler for console use
        formatter = logging.Formatter('%(asctime)s %(name)-20s %(levelname)-8s %(message)s')
        # tell the handler to use this format
        console.setFormatter(formatter)
        # add the handler to the root logger
        logging.getLogger('').addHandler(console)

        parser = ArgumentParser()
        parser.add_argument("-d", "--download", action='count', help="Download data and log into database", default=0)
        parser.add_argument("-f", "--file", help="H5 file name", default='./h5_default.h5')
        parser.add_argument("-m", "--mode", choices=['r', 'r+', 'w', 'a'], help="Mode of opening h5 file", default='a')
        parser.add_argument("-n", "--noise", help="Noises to mix in h5 file", type=str, nargs='+',)
        parser.add_argument("-l", "--limit", help="Number of tracks (0 means all)", type=int, default=0, )
        args = parser.parse_args()

        logging.info('Starting program execution')
        data_manager = DataManager()
        data_manager.main(filename=args.file, mode=args.mode, download=args.download,
                          noises=args.noise, limit=args.limit)
    except Exception as e:
        logging.error('Something was wrong', exc_info=True)
