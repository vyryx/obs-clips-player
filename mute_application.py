from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
from comtypes import CLSCTX_ALL

def mute_applications(app_names, mute=True):
    """Mute or unmute a list of applications by their names."""
    sessions = AudioUtilities.GetAllSessions()
    for session in sessions:
        if session.Process:
            process_name = session.Process.name().lower()
            if process_name in [app.lower() for app in app_names]:
                volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                volume.SetMute(mute, None)
                print(f"{'Muted' if mute else 'Unmuted'} application: {process_name}")

if __name__ == "__main__":
    target_apps = input("Enter the names of the applications to mute/unmute (comma-separated, e.g., 'vlc.exe, firefox.exe'): ").strip().split(",")
    action = input("Enter 'mute' to mute or 'unmute' to unmute the applications: ").strip().lower()

    if action == "mute":
        mute_applications(target_apps, mute=True)
    elif action == "unmute":
        mute_applications(target_apps, mute=False)
    else:
        print("Invalid action. Please enter 'mute' or 'unmute'.")
