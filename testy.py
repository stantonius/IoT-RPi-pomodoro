import datetime

token_refresh_frequency = 60

print(datetime.datetime.utcnow() + datetime.timedelta(minutes=token_refresh_frequency))