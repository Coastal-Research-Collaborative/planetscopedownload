[![Last Commit](https://img.shields.io/github/last-commit/Coastal-Research-Collaborative/planetscopedownload)](
https://github.com/Coastal-Research-Collaborative/planetscopedownload/commits/)
![GitHub issues](https://img.shields.io/github/issues/Coastal-Research-Collaborative/planetscopedownload)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![GitHub commit activity](https://img.shields.io/github/commit-activity/y/Coastal-Research-Collaborative/planetscopedownload)
# 🌍 planetscopedownload  

**`planetscopedownload`** is a Python package designed to facilitate the downloading of **PlanetScope** imagery from [**Planet Lab's**](https://www.planet.com/) data and orders APIs.

## 📥 Installation  

To install the package directly from GitHub, run:  

```bash
pip install git+https://github.com/Coastal-Research-Collaborative/planetscopedownload.git
```
To upgrade this package, run:
```bash
pip install --no-cache-dir --force-reinstall git+https://github.com/Coastal-Research-Collaborative/planetscopedownload.git
```
or, uninstall then reinstall
```bash
pip uninstall planetscopedownload
```
```bash
pip install git+https://github.com/Coastal-Research-Collaborative/planetscopedownload.git
```
## 🚀 Usage

#### 1️⃣ Import the package
```python
import planetscopedownload
```
#### 2️⃣ Define a Site, Coordinates, and Timeframe
```python
sitename = 'georgiajekyllisland'

coords = [
    [-81.41396967622494, 31.035661672924554],
    [-81.40667406770443, 31.035661672924554],
    [-81.40667406770443, 31.053126706868298],
    [-81.41396967622494, 31.053126706868298],
    [-81.41396967622494, 31.035661672924554]
]

start_date = '2024-07-01'
end_date = '2024-08-30'
```
#### 3️⃣ Download Imagery
```python
data_dir = 'path where imagery will be downloaded'  # Specify where to save images

planetscopedownload.retrieve_imagery(
    sitename='hawaiiwaikiki', 
    start_date=start_date, 
    end_date=end_date, # inclusive
    planet_api_key='Your Planet API Key (instruction in {example_notebook.ipynb})',
    data_dir=data_dir,
    polygon=coords
)
```

