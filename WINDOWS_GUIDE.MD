# 1. Install WSL 2 (PowerShell as Admin)
wsl --install -d Ubuntu

# 2. Inside Ubuntu terminal
sudo apt update
sudo apt install -y python3 git

# 3. Get the files (if you didn't already copy them)
git clone https://github.com/your-repo/ip-rotator.git ~/ip-rotator
# or, from a Windows copy:
cp -r /path/to/windows/copy ~/ip-rotator

# 4. Import VPN profiles (choose your source)
python3 ~/ip-rotator/import_profiles.py

# 5. Start the daemon
python3 ~/ip-rotator/ip_rotator.py --daemon

# 6. Stop when you’re done
python3 ~/ip-rotator/ip_rotator.py --stop