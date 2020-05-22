
import time
import datetime
import board
import digitalio
import adafruit_character_lcd.character_lcd as characterlcd
from gpiozero import Button, Buzzer
from signal import pause
import asyncio
import arrow
import json
import paho.mqtt.client as mqtt
import jwt
import ssl

# LCD & button parameters
lcd_rs = digitalio.DigitalInOut(board.D25)
lcd_en = digitalio.DigitalInOut(board.D24)
lcd_d7 = digitalio.DigitalInOut(board.D22)
lcd_d6 = digitalio.DigitalInOut(board.D18)
lcd_d5 = digitalio.DigitalInOut(board.D17)
lcd_d4 = digitalio.DigitalInOut(board.D23)
lcd_backlight = digitalio.DigitalInOut(board.D26)

lcd_columns = 16
lcd_rows = 2

lcd = characterlcd.Character_LCD_Mono(
    lcd_rs, 
    lcd_en, 
    lcd_d4, 
    lcd_d5, 
    lcd_d6, 
    lcd_d7, 
    lcd_columns, 
    lcd_rows,
    lcd_backlight
)

button = Button(2, hold_time=2)
buzzer = Buzzer(16)

lcd.clear()

# GCP parameters
project_id = 'pomodoro-90fd7'
registry_id = 'raspberry-pi-connection' 
device_id = 'raspi'
private_key_file = 'rsa_private.pem'
algorithm = 'RS256'
cloud_region = 'europe-west1'
ca_certs = 'roots.pem'
mqtt_bridge_hostname = 'mqtt.googleapis.com'
mqtt_bridge_port = 8883
message_type = 'event' 

token_refresh_frequency = 2

# IoT Config
def create_jwt(project_id, private_key_file, algorithm):
    # Create a JWT (https://jwt.io) to establish an MQTT connection.
    token = {
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=token_refresh_frequency),
        'aud': project_id
    }
    with open(private_key_file, 'r') as f:
        private_key = f.read()
    print('Creating JWT using {} from private key file {}'.format(
        algorithm, private_key_file))
    return jwt.encode(token, private_key, algorithm=algorithm)

def error_str(rc):
    # Convert a Paho error to a human readable string.
    return '{}: {}'.format(rc, mqtt.error_string(rc))

class Pomodoro:
    """
    Initiate the pomodoro sequence. Show the current pomodoro count when timer is not started.
    Activate the timer using button. Start/pause 1-click, end double-click.
    """
    def __init__(self):
        self.lcd = characterlcd.Character_LCD_Mono(
            lcd_rs, 
            lcd_en, 
            lcd_d4, 
            lcd_d5, 
            lcd_d6, 
            lcd_d7, 
            lcd_columns, 
            lcd_rows,
            lcd_backlight
        )
        self.lcd.backlight = False
        self.lcd.clear()
        self.active_pomo = False
        self.end_time = None
        self.duration = 0
        self.pause_time = None
        self.secs_remaining = None
        self.state = None
        self.connected = False

    def message(self, msg:str, sec:int=None):
        self.lcd.message = msg
        if sec:
            self.backlight_switch("on", sec)
            time.sleep(sec)
            self.clear()

    def backlight_switch(self, state="off", on_time=None):
        if state == "on":
            self.lcd.backlight = True
        if on_time:
            time.sleep(on_time)
            self.lcd.backlight = False
        if state == "off":
            self.lcd.backlight = False

    def clear(self):
        self.lcd.clear()

    def display_time(self):
        self.message(self.call_time(), 1)

    @staticmethod
    def call_time():
        return arrow.utcnow().to('Europe/London').format('HH:mm:ss')

    def timer(self):
        end = arrow.utcnow().shift(seconds=self.secs_remaining) if self.state == 'paused' else self.end_time
        while (end - arrow.utcnow()).seconds > 0 and self.active_pomo:
            minutes, seconds = divmod((self.end_time - arrow.utcnow()).seconds, 60)
            self.lcd.message = f"{minutes} mins {seconds} secs"
            time.sleep(1)
            self.clear()
        buzzer.beep(0.1, 0.1, 2)

    # Methods required for class connection to GCP IoT
    def wait_for_connection(self, timeout):
        # Wait for the device to become connected.
        total_time = 0
        while not self.connected and total_time < timeout:
            time.sleep(1)
            total_time += 1

        if not self.connected:
            raise RuntimeError('Could not connect to MQTT bridge.')
    
    def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
        # Callback on connection.
        print('Connection Result:', error_str(rc))
        self.connected = True
        self.message('Connected bitch', 3)

    def on_disconnect(self, unused_client, unused_userdata, rc):
        # Callback on disconnect.
        print('Disconnected:', error_str(rc))
        self.connected = False

    def on_publish(self, unused_client, unused_userdata, unused_mid):
        # Callback on PUBACK from the MQTT bridge.
        print('Published message acked.')

    def on_subscribe(self, unused_client, unused_userdata, unused_mid,
                     granted_qos):
        # Callback on SUBACK from the MQTT bridge.
        print('Subscribed: ', granted_qos)
        if granted_qos[0] == 128:
            print('Subscription failed.')

    def on_message(self, unused_client, unused_userdata, message):
        payload = message.payload.decode('utf-8')
        print(f"Received message '{payload}' on topic '{message.topic}' with Qos {message.qos}")

        if not payload:
            return

        data = json.loads(payload)

        # ENTER THINGS TO DO HERE DEPENDING ON DATA
        if data['status'] == 'active':
            self.state = 'active'
            self.duration = data['duration']
            self.end_time = arrow.utcnow().shift(minutes=self.duration)
            self.active_pomo = True
        if data['status'] == 'paused':
            self.state = 'paused'




def main():
    # Iniailising client here as well as after while loop
    # I know this is redundant but I can't figure out how to disconnect 
    # the previous client before getting new JWT
    # If you dont disconnect before reconnecting, the code errors out
    client = mqtt.Client(
                client_id='projects/{}/locations/{}/registries/{}/devices/{}'.format(
                    project_id,
                    cloud_region,
                    registry_id,
                    device_id))

    device = Pomodoro()


    
    try:
        while True:
            
            device.clear()
            
            if client:
                ## Add in here to say if reset and pomodoro in progress, capture the inprogress status here 
                client.disconnect()
                
            client = mqtt.Client(
                client_id='projects/{}/locations/{}/registries/{}/devices/{}'.format(
                    project_id,
                    cloud_region,
                    registry_id,
                    device_id))
            client.username_pw_set(
                username='unused',
                password=create_jwt(
                    project_id,
                    private_key_file,
                    algorithm))
            client.tls_set(ca_certs=ca_certs, tls_version=ssl.PROTOCOL_TLSv1_2)

            jwt_refresh = arrow.utcnow().shift(minutes=token_refresh_frequency-1)

            client.on_connect = device.on_connect
            client.on_publish = device.on_publish
            client.on_disconnect = device.on_disconnect
            client.on_subscribe = device.on_subscribe
            client.on_message = device.on_message
            client.connect(mqtt_bridge_hostname, mqtt_bridge_port)

            mqtt_telemetry_topic = '/devices/{}/events'.format(device_id)
            mqtt_config_topic = '/devices/{}/config'.format(device_id)
            mqtt_command_topic = '/devices/{}/commands/#'.format(device_id)

            # Wait up to 5 seconds for the device to connect.
            #device.wait_for_connection(5)

            client.subscribe(mqtt_config_topic, qos=1)
            client.subscribe(mqtt_command_topic, qos=0)

            client.loop_start()
            
            num_message = 0 

            print("Device end time", device.end_time)
            print('Active pomo', device.active_pomo)
            print('State', device.state)
            
            while arrow.utcnow() < jwt_refresh:     #refresh token 1 min before expiration
                # ALL ACTIONS RECEIVED OR PERFORMED UNDER HERE  
                
                # If button was held - send message.
                if button.is_pressed and device.active_pomo:   
                    device.active_pomo = False
                    device.state = 'paused'
                    device.pause_time = arrow.utcnow()
                    device.secs_remaining = (device.end_time - device.pause_time).seconds
                    num_message += 1
                    # Form payload in JSON format.
                    data = {
                        'state' : device.state,
                        'pause_time': device.pause_time.for_json(),
                        'secs_remaining' : device.secs_remaining
                    }
                    payload = json.dumps(data, indent=4)
                    print('Publishing payload', payload)
                    client.publish(mqtt_telemetry_topic, payload, qos=1)
                    buzzer.beep(0.1, 0.1, 1)
                    # Make sure that message was sent once on press.
                if button.is_pressed and not device.active_pomo:
                    device.message('Start pomo with \nGoogle assistant', 10)

                if device.active_pomo and device.state == 'active':
                    device.backlight_switch("on")
                    if (device.end_time - arrow.utcnow()).seconds > 0:
                        device.clear()
                        minutes, seconds = divmod((device.end_time - arrow.utcnow()).seconds, 60)
                        device.lcd.message = f"{minutes} mins {seconds} secs"
                    else:
                        buzzer.beep(0.1, 0.1, 1)
                        device.active_pomo = False
                        device.state == 'complete'
                        device.message("Pomo done", 10)
                if device.active_pomo and device.state == 'paused':
                    buzzer.beep(0.1, 0.1, 1)
                    device.active_pomo = False
                    device.message('Paused pomo', 10)
                time.sleep(1)

    except KeyboardInterrupt:
        # Exit script on ^C.
        pass
        device.backlight_switch()
        device.clear()
        client.disconnect()
        client.loop_stop()
        print('Exit with ^C. Goodbye!')
            

if __name__ == '__main__':
    main()