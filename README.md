# MineMarshall

Hi team logins are:

Admin account: 
- admin@minemarshall.com

Password:
- password

You each have a regular user account(nothing interesting there at this point), your @connect.qut.edu.au email is the login and the password for all accounts is 'password'

To run, create a virtual environment with python:
```
python -m venv venv
```
Then, activate that virtual environment (this is for windows, please google instructions for any other OS)
```
.\venv\Scripts\activate
```
Then run:

```
pip install -r requirements.txt
```

Followed by:
```
python manage.py migrate
python manage.py runserver
```
