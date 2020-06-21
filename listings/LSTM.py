import logging
from argparse import ArgumentParser
from tensorflow import keras
from tensorflow.keras.callbacks import Callback
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
from tensorflow.keras.layers import LSTM
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.regularizers import l2
from src.models.DataGenerator import DataGenerator, GroupInfo

logger = logging.getLogger('LSTM-based Model')


class ModelSaver(Callback):
    def __init__(self, N):
        self.N = N
        self.batch = 0
        self.epoch = 0

    def on_batch_end(self, batch, logs={}):
        if self.batch % self.N == 0:
            name = './checkpoints/LSTM%16d.h5' % self.batch
            logger.info('Saving model %s' % name)
            self.model.save(name)
        self.batch += 1

    def on_epoch_begin(self, epoch, logs=None):
        self.epoch += 1
        name = './checkpoints/LSTM_epoch%5d.h5' % self.epoch
        logger.info('Saving model %s' % name)
        self.model.save(name)


class LSTMModel:
    def __init__(self, checkpoint=None):
        self.batch_size = 32
        self.reg = 0.05
        self.learning_rate = 1e-2
        self.n_units = 512
        self.decay = 1e-3
        self.input_sampling_rate = 11025
        self.n_samples_window = 1024
        self.n_samples_spectrum = 250
        self.overlap = 0.5
        self.n_time_steps = 1
        self.training_generator = None
        self.saver_callback = None
        if checkpoint:
            logger.info('Model checkpoint input obtained')
            self.__model = keras.models.load_model(checkpoint.replace('\\', '/'))
        else:
            logger.info('Creating new model')
            self.__createModel()

    def __createModel(self):
        regularizer = l2(self.reg)
        self.__model = Sequential()
        self.__model.add(LSTM(self.n_units, input_shape=(self.n_time_steps, self.n_samples_spectrum),
                              return_sequences=True, recurrent_dropout=0.3, activation='relu'))
        self.__model.add(LSTM(self.n_units,
                              return_sequences=True, recurrent_dropout=0.3, activation='relu'))
        self.__model.add(LSTM(self.n_units,
                              return_sequences=False, recurrent_dropout=0.3, activation='relu'))
        self.__model.add(Dense(self.n_samples_spectrum, activation='softmax'))

        model_info = []
        self.__model.summary(print_fn=lambda x: model_info.append(x))
        model_info = '\n\t'.join(model_info)
        logger.info(model_info)

        opt = Adam(lr=self.learning_rate,
                   decay=self.decay
                   )
        self.__model.compile(#loss='mean_squared_error',
                             loss='kullback_leibler_divergence',
                             optimizer=opt,
                             metrics=['acc', 'mse'])
        name = './checkpoints/LSTM_finished.h5'
        self.__model.save(name)

    def save(self, filename):
        logger.info('Save model to file ' + filename)
        self.__model.save(filename)

    def train(self, file_name, epochs, save, n_batches=0):
        self.training_generator = DataGenerator(h5_file_path=file_name, batch_size=32, fft_size=self.n_samples_spectrum,
                                                n_time_steps=self.n_time_steps, n_batches=n_batches)

        self.saver_callback = ModelSaver(save)
        self.__model.fit(self.training_generator,
                         max_queue_size=50,
                         workers=16, epochs=epochs,
                         callbacks=[self.saver_callback])
        # Fit_generator is deprecated
        '''self.__model.fit_generator(generator=self.training_generator,
                                   use_multiprocessing=True,
                                   max_queue_size=50,
                                   workers=16, epochs=epochs,
                                   callbacks=[self.saver_callback])'''


if __name__ == "__main__":
    try:
        # set up logging to file
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(name)-20s %(levelname)-8s %(message)s',
                            datefmt='%m-%d %H:%M',
                            filename='./LSTM.log',
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
        parser.add_argument("-t", "--train", help="Path of the H5 training data", default='')
        parser.add_argument("-e", "--epochs", help="Number of epochs for training the model", type=int, default=20)
        parser.add_argument("-s", "--save", help="Number of epochs for saving the model", type=int, default=400000)
        parser.add_argument("-b", "--batch", help="Number of batches for training", type=int, default=0)
        parser.add_argument("-l", "--load", help="Load model from checkpoint", default='')
        args = parser.parse_args()

        logging.info('Starting program execution')
        if args.load:
            model = LSTMModel(checkpoint=args.load)
        else:
            model = LSTMModel()
        if args.train:
            model.train(file_name=args.train, epochs=args.epochs, save=args.save, n_batches=args.batch)

    except Exception as e:
        logging.error('Something was wrong', exc_info=True)
