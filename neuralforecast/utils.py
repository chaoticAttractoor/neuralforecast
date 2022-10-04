# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/utils.ipynb.

# %% auto 0
__all__ = ['AirPassengers', 'AirPassengersDF', 'unique_id', 'ds', 'y', 'AirPassengersPanel', 'snaive', 'airline1_dummy',
           'airline2_dummy', 'AirPassengersStatic', 'generate_series']

# %% ../nbs/utils.ipynb 3
import random
from itertools import chain

import numpy as np
import pandas as pd

# %% ../nbs/utils.ipynb 6
def generate_series(n_series: int,
                    freq: str = 'D',
                    min_length: int = 50,
                    max_length: int = 500,
                    n_temporal_features: int = 0,
                    n_static_features: int = 0,
                    equal_ends: bool = False,
                    seed: int = 0) -> pd.DataFrame:
    """Generate Synthetic Panel Series.

    Generates `n_series` of frequency `freq` of different lengths in the interval [`min_length`, `max_length`].
    If `n_temporal_features > 0`, then each serie gets temporal features with random values.
    If `n_static_features > 0`, then a static dataframe is returned along the temporal dataframe.
    If `equal_ends == True` then all series end at the same date.

    **Parameters:**<br>
    `n_series`: int, number of series for synthetic panel.<br>
    `min_length`: int, minimal length of synthetic panel's series.<br>
    `max_length`: int, minimal length of synthetic panel's series.<br>
    `n_temporal_features`: int, default=0, number of temporal exogenous variables for synthetic panel's series.<br>
    `n_static_features`: int, default=0, number of static exogenous variables for synthetic panel's series.<br>
    `equal_ends`: bool, if True, series finish in the same date stamp `ds`.<br>
    `freq`: str, frequency of the data, [panda's available frequencies](https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases).<br>

    **Returns:**<br>
    `freq`: pandas.DataFrame, synthetic panel with columns [`unique_id`, `ds`, `y`] and exogenous.
    """
    seasonalities = {'D': 7, 'M': 12}
    season = seasonalities[freq]

    rng = np.random.RandomState(seed)
    series_lengths = rng.randint(min_length, max_length + 1, n_series)
    total_length = series_lengths.sum()

    dates = pd.date_range('2000-01-01', periods=max_length, freq=freq).values
    uids = [
        np.repeat(i, serie_length) for i, serie_length in enumerate(series_lengths)
    ]
    if equal_ends:
        ds = [dates[-serie_length:] for serie_length in series_lengths]
    else:
        ds = [dates[:serie_length] for serie_length in series_lengths]

    y = np.arange(total_length) % season + rng.rand(total_length) * 0.5
    temporal_df = pd.DataFrame(dict(unique_id=chain.from_iterable(uids),
                                    ds=chain.from_iterable(ds),
                                    y=y))

    random.seed(seed)
    for i in range(n_temporal_features):
        random.seed(seed)
        temporal_values = [
            [random.randint(0, 100)] * serie_length for serie_length in series_lengths
        ]
        temporal_df[f'temporal_{i}'] = np.hstack(temporal_values)
        temporal_df[f'temporal_{i}'] = temporal_df[f'temporal_{i}'].astype('category')
        if i == 0:
            temporal_df['y'] = temporal_df['y'] * \
                                  (1 + temporal_df[f'temporal_{i}'].cat.codes)

    temporal_df['unique_id'] = temporal_df['unique_id'].astype('category')
    temporal_df['unique_id'] = temporal_df['unique_id'].cat.as_ordered()
    temporal_df = temporal_df.set_index('unique_id')

    if n_static_features > 0:
        static_features = np.random.uniform(low=0.0, high=1.0, 
                        size=(n_series, n_static_features))
        static_df = pd.DataFrame.from_records(static_features, 
                           columns = [f'static_{i}'for i in  range(n_static_features)])
        
        static_df['unique_id'] = np.arange(n_series)
        static_df['unique_id'] = static_df['unique_id'].astype('category')
        static_df['unique_id'] = static_df['unique_id'].cat.as_ordered()
        static_df = static_df.set_index('unique_id')        

        return temporal_df, static_df

    return temporal_df

# %% ../nbs/utils.ipynb 11
AirPassengers = np.array([112., 118., 132., 129., 121., 135., 148., 148., 136., 119., 104.,
                          118., 115., 126., 141., 135., 125., 149., 170., 170., 158., 133.,
                          114., 140., 145., 150., 178., 163., 172., 178., 199., 199., 184.,
                          162., 146., 166., 171., 180., 193., 181., 183., 218., 230., 242.,
                          209., 191., 172., 194., 196., 196., 236., 235., 229., 243., 264.,
                          272., 237., 211., 180., 201., 204., 188., 235., 227., 234., 264.,
                          302., 293., 259., 229., 203., 229., 242., 233., 267., 269., 270.,
                          315., 364., 347., 312., 274., 237., 278., 284., 277., 317., 313.,
                          318., 374., 413., 405., 355., 306., 271., 306., 315., 301., 356.,
                          348., 355., 422., 465., 467., 404., 347., 305., 336., 340., 318.,
                          362., 348., 363., 435., 491., 505., 404., 359., 310., 337., 360.,
                          342., 406., 396., 420., 472., 548., 559., 463., 407., 362., 405.,
                          417., 391., 419., 461., 472., 535., 622., 606., 508., 461., 390.,
                          432.], dtype=np.float32)

# %% ../nbs/utils.ipynb 12
AirPassengersDF = pd.DataFrame({'unique_id': np.ones(len(AirPassengers)),
                                'ds': pd.date_range(start='1949-01-01',
                                                    periods=len(AirPassengers), freq='M'),
                                'y': AirPassengers})

# %% ../nbs/utils.ipynb 18
# Declare Panel Data
unique_id = np.concatenate([['Airline1']*len(AirPassengers), ['Airline2']*len(AirPassengers)])
ds = np.concatenate([pd.date_range(start='1949-01-01', 
                                   periods=len(AirPassengers), freq='M').values,
                     pd.date_range(start='1949-01-01', 
                                   periods=len(AirPassengers), freq='M').values])
y = np.concatenate([AirPassengers, AirPassengers+300])

AirPassengersPanel = pd.DataFrame({'unique_id': unique_id, 'ds': ds, 'y': y})

# For future exogenous variables
# Declare SeasonalNaive12 and fill first 12 values with y
snaive = AirPassengersPanel.groupby('unique_id')['y'].shift(periods=12).reset_index(drop=True)
AirPassengersPanel['trend'] = range(len(AirPassengersPanel))
AirPassengersPanel['y_[lag12]'] = snaive
AirPassengersPanel['y_[lag12]'].fillna(AirPassengersPanel['y'], inplace=True)

# Declare Static Data
unique_id = np.array(['Airline1', 'Airline2'])
airline1_dummy = [0, 1]
airline2_dummy = [1, 0]
AirPassengersStatic = pd.DataFrame({'unique_id': unique_id,
                                    'airline1': airline1_dummy,
                                    'airline2': airline2_dummy})

AirPassengersPanel.groupby('unique_id').tail(4)