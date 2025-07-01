head to https://dev.twitch.tv/console
to get your api credentials

as OAuth Redirect URLs you can put ``http://localhost``

make changes to the ``resources.ini`` to fit your needs, add the client id and client secret (required for fetching clips)

OBS source will be a 'browser source' - as URL put ``http://localhost:8000/`` or whatever port is in the ``resources.ini``

``launch.py`` will install and launch, after initially running ``launch.py`` you should be abled to just run ``clips_server.py`` - you can add a python script to launch automatically with OBS, otherwise you'll need to run it manually.
