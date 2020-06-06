import audioread
import copy
import logging
import os
import zipfile

from src.DBManager import DBManager
from src.LibrivoxScraper import LibrivoxScraper, Track

logger = logging.getLogger('AudioBooksManager')


class AudioBooksManager:
    def __init__(self, db=DBManager(), driver=None):
        self.db = db
        self.__languages = ['spanish']
        self.__librivoxScraper = LibrivoxScraper(driver)
        self.__books = {}

    def __getBooks(self, language):
        self.__books[language] = self.__librivoxScraper.getBooksByLanguage(language)

    def __removeDuplicated(self, language=''):
        urls = []
        for book in self.__books[language]:
            if book.url in urls:
                logging.info('Book ' + book.title + ' already exist in url ' + book.url + '. Removing this book')
                self.__books[language].remove(book)
            else:
                logging.info('Registering url ' + book.url)
                urls.append(book.url)

    def downloadData(self, dstPath='./downloads', sizeMB=19990):
        try:
            downloadNow = False
            sizeMBDownloaded = 0
            if not os.path.exists(dstPath):
                logger.info('Destination path does not exist. Create folder ' + dstPath)
                os.mkdir(dstPath)
            else:
                logger.info('Destination path already exists.')
            for language in self.__languages:
                logger.info('Getting books for language ' + language)
                self.__getBooks(language)
                logger.info('Removing books withing the same url')
                self.__removeDuplicated(language=language)
                for book in self.__books[language]:
                    trackList = []
                    if book.url == '':
                        continue
                    filename = os.path.join(dstPath, os.path.basename(book.url))
                    book.dummy = os.path.splitext(os.path.basename(book.url))[0]
                    if not os.path.isfile(filename):
                        logger.info('File ' + filename + ' does not exist. Downloading it')
                        downloadNow = True
                        self.__librivoxScraper.downloadFile(url=book.url, filename=filename, downloadLib='requests')
                    else:
                        logger.info('File ' + filename + ' already exists')
                    bookFolder = os.path.join(dstPath, book.dummy)
                    if not os.path.exists(bookFolder):
                        logger.info('Folder ' + bookFolder + ' does not exist. Creating it')
                        os.mkdir(bookFolder)
                    else:
                        logger.info('Folder ' + bookFolder + ' already exists')
                    try:
                        with zipfile.ZipFile(filename, 'r') as zipId:
                            fileList = zipId.namelist()
                            for file in fileList:
                                trackPath = os.path.join(bookFolder, file.title())
                                if not os.path.isfile(trackPath):
                                    logger.info('Unzipping file ' + file.title())
                                    zipId.extract(file, bookFolder)
                                else:
                                    logger.info('File ' + file.title() + ' already exists do not unzip')
                    except zipfile.BadZipFile as e:
                        logging.warn(str(e) + ' Avoiding file ' + filename)
                        continue
                    if downloadNow:
                        if self.db.audioBookExist(book.dummy):
                            logger.info('Data base entree already exists and file just downloaded, updating status ' +
                                        'for old register')
                            self.db.audioBookUpdateStatusByName(book.dummy, 'DELETED')
                    if not (not downloadNow and self.db.audioBookExist(book.dummy)):
                        logger.info('Creating new data base entree for all tracks within file ' + bookFolder)
                        for trackFile in os.listdir(bookFolder):
                            track = copy.copy(book)
                            track.__class__ = Track
                            track.name = trackFile
                            track.path = os.path.join(bookFolder, trackFile)
                            track.nTracks = len(os.listdir(bookFolder))
                            track.zip = filename
                            with audioread.audio_open(track.path) as fId:
                                track.channels   = fId.channels
                                track.sampleRate = fId.samplerate
                                track.duration   = fId.duration
                            trackList.append(track)
                            logger.info('Found file ' + trackFile + 'with:' +
                                        '\n\tPath              ' + track.path +
                                        '\n\tnTracks           ' + str(track.nTracks) +
                                        '\n\tZip               ' + track.zip +
                                        '\n\tChannels          ' + str(track.channels) +
                                        '\n\tSample Rate [sps] ' + str(track.sampleRate) +
                                        '\n\tDuration [secs]   ' + str(track.duration))
                        self.db.audioBookCreate(trackList)
                    sizeMBDownloaded += os.path.getsize(filename)/(10**6)
                    logger.info('Total size downloaded %.3f MBytes' % (sizeMBDownloaded))
                    if sizeMBDownloaded > sizeMB:
                        logger.info('Total size downloaded %.3f MBytes exceeds requested target %.3f MBytes' %
                                    (sizeMBDownloaded, sizeMB))
                        break
                if sizeMBDownloaded > sizeMB:
                    break
        except Exception as e:
            logging.error(str(e), exc_info=True)
            raise


if __name__ == '__main__':
    audioBooksManager = AudioBooksManager(driver=r"C:\Program Files (x86)\Google\ChromeDriver\chromedriver.exe")
    audioBooksManager.downloadData()
