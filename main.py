"""
name: Space 
author: amania
discription: This is NavidromeClient for myself.
"""

import json
import requests
import os
import eel
import tempfile
from pydub import AudioSegment
from pydub.playback import play
from threading import Thread, Lock
from queue import Queue
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('web'))

class NavidromeClient:
    def __init__(self):
        self.first = False
        self.config = self.load_config()
        self.token = self.config['token']
        self.headers = {
            'x-nd-authorization': f'Bearer {self.token}',
            'x-nd-client-unique-id': self.config['id'],
            'User-Agent': 'Space/1.0.0',
        }
        self.current_song = None
        self.player_thread = None
        self.is_playing = False
        self.song_queue = Queue()
        self.queue_lock = Lock()

    def load_config(self):
        if os.path.exists('config.json'):
            with open('config.json', 'r') as f:
                data =  json.load(f)
            if data['url'] == '' or data['token'] == '':
                self.first = True
            return data
            
        else:
            with open('config.json', 'w') as f:
                json.dump({'url': '', 
                           'token': '',
                           'username':'',
                           'subsonicSalt':'',
                           'subsonicToken':'',
                           'id':'',
                           }, f)
            self.first = True
    def save_config(self):
        with open('config.json', 'w') as f:
            json.dump(self.config, f)

    def get_album(self,start:int,end:int,sort:str="name",order:str="ASC"):
        url = self.config['url'] + f'/api/album?_sort={sort}&_order={order}&_start={start}&_end={end}'
        response = requests.get(url, headers=self.headers)
        return response.json()
    
    def get_song_info(self, song_id):
        """Get song info including its suffix."""
        url = self.config['url'] + f'/api/song?_sort=album&_end=0&_start=0&_order=ASC&album_id={song_id}'
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()  # This should return a dict with song details including 'suffix'
        else:
            raise Exception("Failed to get song info")

    def download_song(self, song_id):
        """Download song using OpenSubsonic API and return its file path."""
        song_info = self.get_song_info(song_id)
        suffix = song_info.get('suffix', 'mp3')  # Default to 'mp3' if suffix is missing
        song_title = song_info.get('title', 'unknown')

        # Construct download URL
        username = self.config['username']
        salt = self.config['subsonicSalt']
        token = self.config['subsonicToken']
        url = (self.config['url'] +
               f'/rest/stream.view?u={username}&t={token}&s={salt}&f=json&v=1.8.0&c=Space&id={song_id}')
        
        response = requests.get(url, headers=self.headers, stream=True)
        if response.status_code == 200:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}")
            with open(temp_file.name, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024):
                    f.write(chunk)
            print(f"Downloaded {song_title} to {temp_file.name}")
            return temp_file.name
        else:
            raise Exception("Failed to download song")
    
    def play_next_in_queue(self):
        """Play the next song in the queue."""
        with self.queue_lock:
            if self.song_queue.empty():
                self.is_playing = False
                return
            
            next_song_id = self.song_queue.get()
            try:
                song_path = self.download_song(next_song_id)
                self.current_song = AudioSegment.from_file(song_path)
                self.is_playing = True

                def playback():
                    play(self.current_song)
                    self.is_playing = False
                    self.play_next_in_queue()

                self.player_thread = Thread(target=playback)
                self.player_thread.start()
            except Exception as e:
                print(f"Error playing song: {e}")
                self.is_playing = False

    def add_to_queue(self, song_ids):
        """Add songs to the queue."""
        with self.queue_lock:
            for song_id in song_ids:
                self.song_queue.put(song_id)
            if not self.is_playing:
                self.play_next_in_queue()

    def stop_song(self):
        """Stop the current song and clear the queue."""
        with self.queue_lock:
            while not self.song_queue.empty():
                self.song_queue.get()
        if self.player_thread and self.player_thread.is_alive():
            self.is_playing = False
            self.player_thread.join()


        
navidrome = NavidromeClient()
def main():
    #initilize
    eel.init('app')
    if navidrome.first:
        eel.start('login.html', jinja_templates='templates', mode='chrome', size=(900, 600))
    else:
        eel.start('index.html', jinja_templates='templates', mode='chrome', size=(900, 600))

@eel.expose
def render_template(template_name, **context):
    template = env.get_template(template_name)
    return template.render(context)

@eel.expose
def navidrome_login(server,username,password):
    url = server + '/auth/login'
    data = {"username":username,"password":password}
    response = requests.post(url, json=data)
    if response.status_code == 200:
        data = response.json()
        navidrome.config['url'] = str(server)
        navidrome.config['token'] = data['token']
        navidrome.config['username'] = username
        navidrome.config['subsonicSalt'] = data['subsonicSalt']
        navidrome.config['subsonicToken'] = data['subsonicToken']
        navidrome.config['id'] = data['id']
        navidrome.save_config()
        return '0'
    else:
        data = response.json()
        return data["error"]

@eel.expose
def get_song_art(id):
    username = navidrome.config['username']
    salt = navidrome.config['subsonicSalt']
    token = navidrome.config['subsonicToken']
    url = navidrome.config['url'] + f'/rest/getCoverArt?u={username}&t={token}&s={salt}&f=json&v=1.8.0&c=Space&id={id}&size=300'
    return url
    
@eel.expose
def get_album(start:int,end:int,sort:str="name",order:str="ASC"):
    return navidrome.get_album(start,end,sort,order)

@eel.expose
def get_album_info(id):
    url = navidrome.config['url'] + f'/api/album?id={id}'
    response = requests.get(url, headers=navidrome.headers)
    return response.json()

@eel.expose
def get_album_songs(id):
    url = navidrome.config['url'] + f'/api/song?_sort=album&_end=0&_start=0&_order=ASC&album_id={id}'
    response = requests.get(url, headers=navidrome.headers)
    return response.json()

@eel.expose
def play_songs(song_ids):
    try:
        navidrome.add_to_queue(song_ids)
        return "Songs added to queue"
    except Exception as e:
        return str(e)

@eel.expose
def stop_song():
    navidrome.stop_song()
    return "Stopped"



if __name__ == '__main__':
    main()