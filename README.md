# Smarter-Emergency-Dispatch (SmartDispatch)

###### Our Mission
Fire and ambulance services across the country depend on technology to help save lives. That technology is sorely outdated, has caused dangerous delays and even cost people their lives. SmartDispatch aides emergency care dispatchers in distributing ambulances according to emergency service (EMS) distributions to improve response times, reduce cost, and reduce human error.

Smart Dispatch addresses three key obstacles dispatchers face.

###### How many calls will happen and where?
Most dispatching systems in use today do not have any predictive components. However, many municipalities maintain records of emergency calls and response times that stretch back years. SmartDispatch leverages this historical data to predict the number of calls in a given area on an hourly basis, so dispatchers have a clearer understanding of what to expect.

###### Who should respond to each call?
Dispatchers often rely on institutional and geographic knowledge of their regions to assign emergency units to calls. This means critical choices in sometimes life-threatening situations are vulnerable to human error and bias. SmartDispatch automates these choices and accounts for existing traffic conditions. Response times are minimized, and dispatchers can focus on other critical tasks.

###### Where should ambulances wait while not in service?
Unlike brick and mortar firehouses, ambulances and emergency vehicles don't have fixed stations at which to wait while not responding to a call. Instead, planners and dispatchers must choose post locations for their ambulances. SmartDispatch addresses these inconsistencies by assigning post locations that position ambulances nearest the areas with the highest concentration of predicted calls.

---

# Running SmartDispatch on Windows with Python 3.13

## Prerequisites

- Python 3.13.x installed and on your PATH
- A Google Maps API key (for geocoding and dispatch features)

## First-time Setup

```powershell
cd "D:\Area-51\Smarter-Emergency-Dispatch-master"
python -m venv venv
venv\Scripts\activate
python --version   # must show Python 3.13.x
pip install -r requirements.txt

cd test\test
python manage.py migrate
python manage.py generate_fake_data
```

## Starting the Server

```powershell
cd "D:\Area-51\Smarter-Emergency-Dispatch-master"
venv\Scripts\activate
$env:GGL_API_KEY="YOUR_GOOGLE_MAPS_API_KEY"
cd test\test
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser.

## Reset / Reseed

If ambulance positions get corrupted or you want a fresh start:

```powershell
python manage.py generate_fake_data
```

This regenerates all historical data AND re-runs K-Means to optimally position ambulances.

## Running the ML Notebooks

```powershell
cd "D:\Area-51\Smarter-Emergency-Dispatch-master"
venv\Scripts\activate
pip install jupyter notebook ipykernel
jupyter notebook
```

Then open any of the notebooks in `models/`:
- `0 - Baseline Model.ipynb`
- `1 - NN model.ipynb`
- `2 - LSTM model.ipynb`
- `3 - XGB Model.ipynb`

Extract the data archive first:
```powershell
# Extract the EMS calls dataset (required by notebooks)
Expand-Archive -Path data\ems_calls_resampled_v2.zip -DestinationPath data\
```

---

## Application Structure

```
Smarter-Emergency-Dispatch-master/
├── venv/                         ← Python virtual environment (not committed)
├── requirements.txt              ← All Python dependencies
├── .gitignore
├── data/                         ← EMS call data and shapefiles
├── models/                       ← ML notebooks (Baseline, NN, LSTM, XGBoost)
├── archive/                      ← Original Docker/Django source (reference only)
└── test/test/                    ← Django application root
    ├── manage.py
    ├── db.sqlite3                 ← SQLite database (created after migrate)
    ├── model_2_funcs.py          ← Ambulance placement optimization
    ├── load_data.py              ← Seed script for initial data
    ├── test/                     ← Django project package (settings, urls, celery)
    ├── map/                      ← Main dispatch app (models, views, forms, tasks)
    └── django_sb_admin/          ← SB Admin UI wrapper app
```

---

## Modernization Summary (from Django 1.11 → Django 5.1 / Python 3.13)

| Component | Old | New |
|---|---|---|
| Python | 2/3 (3.6-era) | **3.13.7** |
| Django | 1.11.5 | **5.1.4** |
| Celery integration | `django-celery` / `djcelery` | **Celery 5.4** (native Django integration) |
| URL routing | `url()` with regex | `path()` |
| Settings | Hardcoded absolute paths | Relative `Path(__file__)` based |
| Template DIRS | `/Users/priyagupta/...` | Empty — uses `APP_DIRS=True` |
| Database path | `os.path.join(BASE_DIR, ...)` string | `BASE_DIR / 'db.sqlite3'` Path object |
| geopandas API | `geopandas.geoseries.GeoSeries/Point` | `geopandas.GeoSeries` + `shapely.geometry.Point` |
| folium API | `RegularPolygonMarker` (removed) | `CircleMarker` |
| pandas API | `DataFrame.append()` (removed) | `pd.concat()` |
| GeoDataFrame CRS | `gdf.crs = {'init': 'epsg:4326'}` | `gdf.set_crs('epsg:4326')` |
| API key | Hardcoded `os.environ['GGL_API_KEY']` (crashes if missing) | `os.environ.get('GGL_API_KEY', '')` (safe default) |
| `DEFAULT_AUTO_FIELD` | Not set (deprecation warning) | Set to `BigAutoField` |

### Notes on Celery
The original project used `django-celery` which is incompatible with Python 3 / modern Django.
It has been replaced with Celery 5.4's native Django integration. For local development, tasks are configured to run **eagerly** (synchronously) via `CELERY_TASK_ALWAYS_EAGER = True`, so the Django server works without needing a RabbitMQ or Redis broker.

To run the hourly prediction refresh task with a real broker, install Redis and set:
```powershell
$env:CELERY_BROKER_URL="redis://localhost:6379/0"
```

### Features Preserved
- All 6 database models (Event_feed, Predictions, Ambulance, EMS_Calls, Current_predictions, Current_ambulance)
- Ambulance dispatch logic with Google Maps Distance Matrix API
- EMS call intake and geocoding
- Folium choropleth map generation (predicted call density by zip code)
- Ambulance placement optimization (Model 2 / KMeans)
- Event feed table
- All ML notebooks

###### Contact
Melanie Costello: melanie.costello@berkeley.edu  
Priya Gupta: priyagupta@berkeley.edu  
Jason Harville: jlharville@berkeley.edu  
James Peng: james.y.peng@berkeley.edu
