# MineMarshall — Setup & Installation Guide


## Windows Users: Set Up Windows Subsystem for Linux
All Windows instructions in this guide assume you are using **WSL with Ubuntu/Debian**. PostGIS was unable to operate with Django on a native windows installation.

### Install WSL2

Open **PowerShell as Administrator** and run:

```powershell
wsl --install
```

When prompted, reboot your system.

Once rebooted, WSL should come with Ubuntu by default, if not, you can install it with:

```powershell
wsl --install -d Ubuntu
``` 

Complete the initial setup (create a Linux username and password).

> All subsequent steps in this guide should be run inside the **Ubuntu WSL terminal**, not PowerShell or Command Prompt.

### Clone inside the WSL filesystem

For best performance, work within the WSL filesystem rather than a Windows drive mount:

```bash
cd ~
```

Then proceed to Section 1.


## Mac Users: Ensure Homebrew is installed

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
---

## 1. Clone the Repository

```bash
git clone https://github.com/lkemp7/MineMarshall.git
cd MineMarshall
```

---

## 2. Create a Virtual Environment

Ensure python is installed 

### Linux/WSL:
```bash
sudo apt install python3 python3-venv
python3 -m venv venv
source venv/bin/activate
```
You should see `(venv)` in your terminal prompt once activated.
### Mac:

```bash
brew install python@3.12
python3.12 -m venv venv
source venv/bin/activate
```
You should see `(venv)` in your terminal prompt once activated.

### After activating your virtual environment, ensure pip is updated:
```python
python -m pip install --upgrade pip
```



---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs all python packages required for the application.

For the additional system packages, run:

### Linux/WSL

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib postgis gdal-bin libgdal-dev binutils libproj-dev curl zstd
```
### Mac:
```bash
brew install postgresql postgis gdal proj zstd
```
## 3.1: Install ollama:

### Linux/WSL:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```
Then, install the llama 3.2:3b model
```bash
ollama pull llama3.2:3b
```

### Mac:
```bash
brew install ollama
brew services start ollama
```
Then, install the llama 3.2:3b model

```bash
ollama pull llama3.2:3b
```

## 4. Set up the database
### Linux/WSL: Connect to PostgreSQL:

```bash
sudo -u postgres psql
```
### Mac: Connect to PostgreSQL:

```bash
brew services start postgresql
psql postgres
```
### All operating systems:
Run each command **individually**:

```sql
CREATE DATABASE minemarshall;
```
```sql
CREATE USER minemarshall_admin WITH PASSWORD 'your_password';
```
```sql
GRANT ALL PRIVILEGES ON DATABASE minemarshall TO minemarshall_admin;
```

Connect to the new database:

```sql
\c minemarshall
```

Grant schema permissions:

```sql
GRANT ALL ON SCHEMA public TO minemarshall_admin;
```

Enable the PostGIS extension:

```sql
CREATE EXTENSION postgis;
```

Exit psql:

```sql
\q
```

### Verify PostGIS is active (optional)

**Linux / WSL:**
```bash
sudo -u postgres psql -d minemarshall -c "SELECT PostGIS_Version();"
```

**macOS:**
```bash
psql minemarshall -c "SELECT PostGIS_Version();"
```

---

## 5. Configure Django Database

Update the following block in the settings.py (line 80) file to match the user credentials you have just created for the database.

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'minemarshall',
        'USER': 'minemarshall_admin',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

---

## 6. Run Database Migrations

```bash
python manage.py migrate
```

This applies all schema migrations to the database.

---

## 7. Create a Superuser (Admin Account)

```bash
python manage.py createsuperuser
```

Follow the prompts to set an email address and password. This account will have Admin-level access in MineMarshall.

---

## 8. Start the Development Server

```bash
python manage.py runserver
```

Open your browser and go to:

```
http://127.0.0.1:8000
```

## 9. Email Integration

For the email integration, a gmail account is currently used. If you want to switch this to another service, the relevant settings are at like 147-153 of ./MineMarshall/settings.py