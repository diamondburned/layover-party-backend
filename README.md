# Layover Party

## Description

An app that allows you to look for flights that have long layovers to visit more places as you travel

## Running

1. Install python 3.11.2

2. Set up environment
```
python -m venv venv
source venv/bin/activate
```

3. Install dependencies
```
python -m pip install -r requirements.txt
```

4. Run api

```
./run.sh
```

## Code

Python Import Structure

```py
# standard lib
import datetime

# pip packages
from fastapi import FastAPI

# our code
from db import db
```
