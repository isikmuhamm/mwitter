import tweepy

# Your Twitter API credentials
API_KEY = 'your-api-key'
API_SECRET_KEY = 'your-api-secret-key'
ACCESS_TOKEN = 'your-access-token'
ACCESS_TOKEN_SECRET = 'your-access-token-secret'

# Authenticate to Twitter
auth = tweepy.OAuth1UserHandler(API_KEY, API_SECRET_KEY, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
api = tweepy.API(auth)

# Create a tweet
tweet = "Hello, world! This is an automated tweet from my script."
api.update_status(status=tweet)

print("Tweet posted successfully!")
