from TwitterAPI import TwitterAPI
import threading
import json
import os.path
import random
import logging


logging.basicConfig()
logger = logging.getLogger(__name__)


class IgnoreList(list):
    """List class writing the data in a file.
    """

    def append(self, item):
        super(IgnoreList, self).append(item)

        # Store to a file
        with open('ignorelist', 'a') as f:
            f.write(item + '\n')


class TwitterContest():
    def __init__(self):
        """Init the user config from config.json. Start Twitter API and load
        ignore list.
        """
        # Load our configuration from the JSON file.
        with open('config.json') as data_file:
            data = json.load(data_file)

        # These vars are loaded in from config.
        self.consumer_key = data['consumer-key']
        self.consumer_secret = data['consumer-secret']
        self.access_token_key = data['access-token-key']
        self.access_token_secret = data['access-token-secret']
        self.retweet_update_time = data['retweet-update-time']
        self.quote_update_time = data['quote-update-time']
        self.scan_update_time = data['scan-update-time']
        self.search_queries = data['search-queries']
        self.follow_keywords = data['follow-keywords']
        self.fav_keywords = data['fav-keywords']
        self.ignore_users = data['ignore-users']

        # Don't edit these unless you know what you're doing.
        self.api = TwitterAPI(self.consumer_key, self.consumer_secret,
                              self.access_token_key, self.access_token_secret)
        self.rt_list = list()
        self.ignore_list = IgnoreList()

        if os.path.isfile('ignorelist'):
            logger.info(u'Loading ignore list...')
            with open('ignorelist', 'r') as f:
                self.ignore_list = IgnoreList(f.read().splitlines())
            logger.info(u'Loaded {0} elements in ignore list'.format(self.ignore_list))

    def post_quote(self):
            """Post a random quote (avoid beeing flagged as spam...).
            """
            t = threading.Timer(self.quote_update_time, self.post_quote)
            t.start()

            quote_index = random.randint(1, 76233)
            quote_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'quotes.txt')

            logger.info(u'Tweeting quote nb {0}'.format(quote_index))

            with open(quote_file) as f:
                for i, line in enumerate(f):
                    if i == quote_index - 1:  # Tweet quote
                        start = 0
                        stop = 139
                        while True:
                            if start + 140 < len(line):  # It is only the beginning...
                                self.api.request('statuses/update', {'status': line[start:stop - 3] + '...'})
                                start += 136
                                stop += 136
                            else:  # End of the quote
                                self.api.request('statuses/update', {'status': line[start:stop]})
                                break

    def update_rt_queue(self):
        """Update the Retweet queue (this prevents too many retweets happening at once).
        """
        t = threading.Timer(self.retweet_update_time, self.update_rt_queue)
        t.start()

        logger.info(u'=== CHECKING RETWEET QUEUE ===')
        logger.debug(u'Queue length: {}'.format(str(len(self.rt_list))))

        if len(self.rt_list) > 0:
            rt = self.rt_list[0]
            logger.debug(u'Retweeting {0}: {1}'.format(str(rt['id']), str(rt['text'].encode('utf8'))))

            self.check_for_follow(rt)
            self.check_for_favorite(rt)

            self.api.request('statuses/retweet/:{}'.format(str(rt['id'])))
            self.rt_list.pop(0)

    def check_for_follow(self, tweet):
        """Check if a post requires you to follow the user.

        Args:
            tweet: the tweet to check.
        """
        text = tweet['text']

        if any(x in text.lower() for x in self.follow_keywords):
            users = []
            if 'retweeted_status' in tweet:  # Follow original user
                users.append(tweet['retweeted_status']['user']['screen_name'])
            else:
                users.append(tweet['user']['screen_name'])

            # Add user mentioned in tweet
            for user in tweet['entities']['user_mentions']:
                users.append(user['screen_name'])

            for user in users:
                try:
                    self.api.request('friendships/create', {'screen_name': user})
                    logger.info(u'Follow: {}'.format(user))
                except:
                    pass

    def check_for_favorite(self, tweet):
        """Check if a post requires you to favorite the tweet.

        Args:
            tweet: the tweet to check.
        """
        text = tweet['text']
        if any(x in text.lower() for x in self.fav_keywords):
            try:
                self.api.request('favorites/create', {'id': tweet['retweeted_status']['user']['id']})
                logger.info(u'Favorite: {}'.format(str(tweet['retweeted_status']['user']['id'])))
            except:
                self.api.request('favorites/create', {'id': tweet['id']})
                logger.info(u'Favorite: {}'.format(str(tweet['id'])))

    def scan_for_contests(self):
        """Scan for new contests.
        """
        t = threading.Timer(self.scan_update_time, self.scan_for_contests)
        t.start()

        logger.info(u'=== SCANNING FOR NEW CONTESTS ===')

        for search_query in self.search_queries:
            logger.info(u'Getting new results for: {}'.format(search_query))

            request = self.api.request('search/tweets', {'q': search_query, 'result_type': 'mixed', 'count': 100})
            counter = 0
            for tweet in request:
                counter += 1
                ignore = False

                # Get tweet data
                if 'retweeted_status' in tweet:  # The tweet is a RT
                    original = tweet['retweeted_status']
                    id = str(original['id'])
                    user = original['user']
                    user_screen_name = original['screen_name']
                    text = original['text']

                    # Check text of original_item
                    keywords = search_query.split(' ')
                    keywords = [x for x in keywords if not x[0] == '-']  # Exclude "-query"
                    if not all(x in text for x in keywords):
                        ignore = True  # Rt does not match query
                else:  # Classic tweet
                    user = tweet['user']
                    user_screen_name = user['screen_name']
                    text = tweet['text'].replace('\n', '')
                    id = str(tweet['id'])

                if not ignore:
                    if id not in self.ignore_list:
                        if user_screen_name not in self.ignore_list and user_screen_name not in self.ignore_users:
                            if tweet['retweet_count'] > 0:  # The tweet already has RT (credibility)
                                self.rt_list.append(tweet)
                                logger.info(u'Added to queue: {0} - {1}: {2}'.format(id, user_screen_name, text))
                                self.ignore_list.append(id)
                        else:
                            logger.info(u'{} in ignore list'.format(user_screen_name))
                    else:
                        logger.info(u'{} in ignore list'.format(id))

            logger.info(u'Got {} results.'.format(str(counter)))

    def run(self):
        """Run the twitter contest bot.
        """
        self.post_quote()
        self.scan_for_contests()
        self.update_rt_queue()
