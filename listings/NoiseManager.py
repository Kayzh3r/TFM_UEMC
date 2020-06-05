from __future__ import unicode_literals
import audioread
import logging
import os
import youtube_dl

from src.DBManager import DBManager

logger = logging.getLogger('NoiseManager')


class NoiseManager:
    def __init__(self, db=DBManager()):
        self.resources = {
            'airDryer': 'https://www.youtube.com/watch?v=PNAGqh2h3AA',
            'serverRoom': 'https://www.youtube.com/watch?v=gLLvXi1Usrc',
            'coffeeShop': 'https://www.youtube.com/watch?v=BOdLmxy06H0',
            'crowd': 'https://www.youtube.com/watch?v=IKB3Qiglyro',
            'peopleTalking': 'https://www.youtube.com/watch?v=PHBJNN-M_Mo',
            'cityRain': 'https://www.youtube.com/watch?v=eZe4Q_58UTU',
            'city1': 'https://www.youtube.com/watch?v=cDWZkXjDYsc',
            'city2': 'https://www.youtube.com/watch?v=YF3pj_3mdMc',
            'city3': 'https://www.youtube.com/watch?v=8s5H76F3SIs',
            'city4': 'https://www.youtube.com/watch?v=Vg1mpD1BICI'
        }
        self.ydl_opts = {
            'format': 'bestaudio/best',
            ''' 'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],'''
            'outtmpl': '',
        }
        self.db = db

    def downloadData(self, dstPath='./downloads'):
        downloadNow = False
        if not os.path.exists(dstPath):
            logger.info('Destination path does not exist. Create folder ' + dstPath)
            os.mkdir(dstPath)
        else:
            logger.info('Destination path already exists.')
        for key in self.resources:
            filename = os.path.join(dstPath, key)
            if not os.path.isfile(filename):
                logger.info('File ' + filename + ' does not exist. Downloading it')
                downloadNow = True
                self.ydl_opts['outtmpl'] = filename
                with youtube_dl.YoutubeDL(self.ydl_opts) as ydl:
                    success = ydl.download([self.resources[key]])
            else:
                logger.info('File ' + filename + ' already exists')
            if downloadNow:
                if self.db.noiseExist(key):
                    logger.info('Data base entree already exists and file just downloaded, updating status ' +
                                'for old register')
                    self.db.noiseUpdateStatusByName(key, 'DELETED')
            if not (not downloadNow and self.db.noiseExist(key)):
                with audioread.audio_open(filename) as fId:
                    logger.info('Creating new data base entree for noise file ' + filename + ' with:' +
                                '\n\tChannels          ' + str(fId.channels) +
                                '\n\tSample Rate [sps] ' + str(fId.samplerate) +
                                '\n\tDuration [secs]   ' + str(fId.duration))
                    self.db.noiseCreate(key, self.resources[key],
                                        filename, fId.channels,
                                        fId.samplerate, fId.duration)


if __name__ == '__main__':
    noiseManager = NoiseManager()
    noiseManager.downloadData()
