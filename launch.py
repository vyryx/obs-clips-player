import subprocess
import sys
import os
import venv

def create_virtual_environment():
    """Create a virtual environment if it doesn't exist"""
    venv_dir = os.path.join(os.path.dirname(__file__), ".venv")
    if not os.path.exists(venv_dir):
        print("Creating virtual environment...")
        venv.create(venv_dir, with_pip=True)
        print("Virtual environment created.")
    return venv_dir

def install_requirements(venv_dir):
    """Install dependencies from requirements.txt"""
    requirements_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
    pip_executable = os.path.join(venv_dir, "Scripts", "pip") if os.name == "nt" else os.path.join(venv_dir, "bin", "pip")
    if os.path.exists(requirements_file):
        try:
            subprocess.check_call([pip_executable, "install", "-r", requirements_file])
            print("Dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to install dependencies: {e}")
            sys.exit(1)
    else:
        print("requirements.txt not found. Skipping dependency installation.")

def launch_clips_server(venv_dir):
    """Launch the clips_server.py script."""
    clips_server_path = os.path.join(os.path.dirname(__file__), "clips_server.py")
    python_executable = os.path.join(venv_dir, "Scripts", "python") if os.name == "nt" else os.path.join(venv_dir, "bin", "python")
    if os.path.exists(clips_server_path):
        try:
            subprocess.check_call([python_executable, clips_server_path])
        except subprocess.CalledProcessError as e:
            print(f"Failed to launch clips_server.py: {e}")
    else:
        print("clips_server.py not found. Ensure the file exists in the same directory.")

if __name__ == "__main__":
    venv_dir = create_virtual_environment()
    install_requirements(venv_dir)
    launch_clips_server(venv_dir)
