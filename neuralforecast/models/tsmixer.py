# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/models.tsmixer.ipynb.

# %% auto 0
__all__ = ['TSMixer']

# %% ../../nbs/models.tsmixer.ipynb 5
import torch
import torch.nn as nn
import torch.nn.functional as F

from typing import Optional
from ..losses.pytorch import MAE
from ..common._base_model import BaseModel

# %% ../../nbs/models.tsmixer.ipynb 8
class TemporalMixing(nn.Module):
    def __init__(self, n_series, input_size, dropout):
        super().__init__()
        self.temporal_norm = nn.BatchNorm1d(
            num_features=n_series * input_size, eps=0.001, momentum=0.01
        )
        self.temporal_lin = nn.Linear(input_size, input_size)
        self.temporal_drop = nn.Dropout(dropout)

    def forward(self, input):
        # Get shapes
        batch_size = input.shape[0]
        input_size = input.shape[1]
        n_series = input.shape[2]

        # Temporal MLP
        x = input.permute(0, 2, 1)  # [B, L, N] -> [B, N, L]
        x = x.reshape(batch_size, -1)  # [B, N, L] -> [B, N * L]
        x = self.temporal_norm(x)  # [B, N * L] -> [B, N * L]
        x = x.reshape(batch_size, n_series, input_size)  # [B, N * L] -> [B, N, L]
        x = F.relu(self.temporal_lin(x))  # [B, N, L] -> [B, N, L]
        x = x.permute(0, 2, 1)  # [B, N, L] -> [B, L, N]
        x = self.temporal_drop(x)  # [B, L, N] -> [B, L, N]

        return x + input


class FeatureMixing(nn.Module):
    def __init__(self, n_series, input_size, dropout, ff_dim):
        super().__init__()
        self.feature_norm = nn.BatchNorm1d(
            num_features=n_series * input_size, eps=0.001, momentum=0.01
        )
        self.feature_lin_1 = nn.Linear(n_series, ff_dim)
        self.feature_lin_2 = nn.Linear(ff_dim, n_series)
        self.feature_drop_1 = nn.Dropout(dropout)
        self.feature_drop_2 = nn.Dropout(dropout)

    def forward(self, input):
        # Get shapes
        batch_size = input.shape[0]
        input_size = input.shape[1]
        n_series = input.shape[2]

        # Feature MLP
        x = input.reshape(batch_size, -1)  # [B, L, N] -> [B, L * N]
        x = self.feature_norm(x)  # [B, L * N] -> [B, L * N]
        x = x.reshape(batch_size, input_size, n_series)  # [B, L * N] -> [B, L, N]
        x = F.relu(self.feature_lin_1(x))  # [B, L, N] -> [B, L, ff_dim]
        x = self.feature_drop_1(x)  # [B, L, ff_dim] -> [B, L, ff_dim]
        x = self.feature_lin_2(x)  # [B, L, ff_dim] -> [B, L, N]
        x = self.feature_drop_2(x)  # [B, L, N] -> [B, L, N]

        return x + input


class MixingLayer(nn.Module):
    def __init__(self, n_series, input_size, dropout, ff_dim):
        super().__init__()
        # Mixing layer consists of a temporal and feature mixer
        self.temporal_mixer = TemporalMixing(n_series, input_size, dropout)
        self.feature_mixer = FeatureMixing(n_series, input_size, dropout, ff_dim)

    def forward(self, input):
        x = self.temporal_mixer(input)
        x = self.feature_mixer(x)
        return x

# %% ../../nbs/models.tsmixer.ipynb 10
class ReversibleInstanceNorm1d(nn.Module):
    def __init__(self, n_series, eps=1e-5):
        super().__init__()
        self.weight = nn.Parameter(torch.ones((1, 1, n_series)))
        self.bias = nn.Parameter(torch.zeros((1, 1, n_series)))

        self.eps = eps

    def forward(self, x):
        # Batch statistics
        self.batch_mean = torch.mean(x, axis=1, keepdim=True).detach()
        self.batch_std = torch.sqrt(
            torch.var(x, axis=1, keepdim=True, unbiased=False) + self.eps
        ).detach()

        # Instance normalization
        x = x - self.batch_mean
        x = x / self.batch_std
        x = x * self.weight
        x = x + self.bias

        return x

    def reverse(self, x):
        # Reverse the normalization
        x = x - self.bias
        x = x / self.weight
        x = x * self.batch_std
        x = x + self.batch_mean

        return x

# %% ../../nbs/models.tsmixer.ipynb 12
class TSMixer(BaseModel):
    """TSMixer

    Time-Series Mixer (`TSMixer`) is a MLP-based multivariate time-series forecasting model. `TSMixer` jointly learns temporal and cross-sectional representations of the time-series by repeatedly combining time- and feature information using stacked mixing layers. A mixing layer consists of a sequential time- and feature Multi Layer Perceptron (`MLP`).

    **Parameters:**<br>
    `h`: int, forecast horizon.<br>
    `input_size`: int, considered autorregresive inputs (lags), y=[1,2,3,4] input_size=2 -> lags=[1,2].<br>
    `n_series`: int, number of time-series.<br>
    `futr_exog_list`: str list, future exogenous columns.<br>
    `hist_exog_list`: str list, historic exogenous columns.<br>
    `stat_exog_list`: str list, static exogenous columns.<br>
    `n_block`: int=2, number of mixing layers in the model.<br>
    `ff_dim`: int=64, number of units for the second feed-forward layer in the feature MLP.<br>
    `dropout`: float=0.9, dropout rate between (0, 1) .<br>
    `revin`: bool=True, if True uses Reverse Instance Normalization to process inputs and outputs.<br>
    `loss`: PyTorch module, instantiated train loss class from [losses collection](https://nixtla.github.io/neuralforecast/losses.pytorch.html).<br>
    `valid_loss`: PyTorch module=`loss`, instantiated valid loss class from [losses collection](https://nixtla.github.io/neuralforecast/losses.pytorch.html).<br>
    `max_steps`: int=1000, maximum number of training steps.<br>
    `learning_rate`: float=1e-3, Learning rate between (0, 1).<br>
    `num_lr_decays`: int=-1, Number of learning rate decays, evenly distributed across max_steps.<br>
    `early_stop_patience_steps`: int=-1, Number of validation iterations before early stopping.<br>
    `val_check_steps`: int=100, Number of training steps between every validation loss check.<br>
    `batch_size`: int=32, number of different series in each batch.<br>
    `step_size`: int=1, step size between each window of temporal data.<br>
    `scaler_type`: str='identity', type of scaler for temporal inputs normalization see [temporal scalers](https://nixtla.github.io/neuralforecast/common.scalers.html).<br>
    `random_seed`: int=1, random_seed for pytorch initializer and numpy generators.<br>
    `num_workers_loader`: int=os.cpu_count(), workers to be used by `TimeSeriesDataLoader`.<br>
    `drop_last_loader`: bool=False, if True `TimeSeriesDataLoader` drops last non-full batch.<br>
    `alias`: str, optional,  Custom name of the model.<br>
    `optimizer`: Subclass of 'torch.optim.Optimizer', optional, user specified optimizer instead of the default choice (Adam).<br>
    `optimizer_kwargs`: dict, optional, list of parameters used by the user specified `optimizer`.<br>
    `lr_scheduler`: Subclass of 'torch.optim.lr_scheduler.LRScheduler', optional, user specified lr_scheduler instead of the default choice (StepLR).<br>
    `lr_scheduler_kwargs`: dict, optional, list of parameters used by the user specified `lr_scheduler`.<br>
    `**trainer_kwargs`: int,  keyword trainer arguments inherited from [PyTorch Lighning's trainer](https://pytorch-lightning.readthedocs.io/en/stable/api/pytorch_lightning.trainer.trainer.Trainer.html?highlight=trainer).<br>

    **References:**<br>
    - [Chen, Si-An, Chun-Liang Li, Nate Yoder, Sercan O. Arik, and Tomas Pfister (2023). "TSMixer: An All-MLP Architecture for Time Series Forecasting."](http://arxiv.org/abs/2303.06053)

    """

    # Class attributes
    EXOGENOUS_FUTR = False
    EXOGENOUS_HIST = False
    EXOGENOUS_STAT = False
    MULTIVARIATE = True  # If the model produces multivariate forecasts (True) or univariate (False)
    RECURRENT = (
        False  # If the model produces forecasts recursively (True) or direct (False)
    )

    def __init__(
        self,
        h,
        input_size,
        n_series,
        futr_exog_list=None,
        hist_exog_list=None,
        stat_exog_list=None,
        exclude_insample_y=False,
        n_block=2,
        ff_dim=64,
        dropout=0.9,
        revin=True,
        loss=MAE(),
        valid_loss=None,
        max_steps: int = 1000,
        learning_rate: float = 1e-3,
        num_lr_decays: int = -1,
        early_stop_patience_steps: int = -1,
        val_check_steps: int = 100,
        batch_size: int = 32,
        valid_batch_size: Optional[int] = None,
        windows_batch_size=1024,
        inference_windows_batch_size=1024,
        start_padding_enabled=False,
        step_size: int = 1,
        scaler_type: str = "identity",
        random_seed: int = 1,
        num_workers_loader: int = 0,
        drop_last_loader: bool = False,
        optimizer=None,
        optimizer_kwargs=None,
        lr_scheduler=None,
        lr_scheduler_kwargs=None,
        **trainer_kwargs
    ):

        # Inherit BaseMultivariate class
        super(TSMixer, self).__init__(
            h=h,
            input_size=input_size,
            n_series=n_series,
            futr_exog_list=futr_exog_list,
            hist_exog_list=hist_exog_list,
            stat_exog_list=stat_exog_list,
            exclude_insample_y=exclude_insample_y,
            loss=loss,
            valid_loss=valid_loss,
            max_steps=max_steps,
            learning_rate=learning_rate,
            num_lr_decays=num_lr_decays,
            early_stop_patience_steps=early_stop_patience_steps,
            val_check_steps=val_check_steps,
            batch_size=batch_size,
            valid_batch_size=valid_batch_size,
            windows_batch_size=windows_batch_size,
            inference_windows_batch_size=inference_windows_batch_size,
            start_padding_enabled=start_padding_enabled,
            step_size=step_size,
            scaler_type=scaler_type,
            random_seed=random_seed,
            num_workers_loader=num_workers_loader,
            drop_last_loader=drop_last_loader,
            optimizer=optimizer,
            optimizer_kwargs=optimizer_kwargs,
            lr_scheduler=lr_scheduler,
            lr_scheduler_kwargs=lr_scheduler_kwargs,
            **trainer_kwargs
        )

        # Reversible InstanceNormalization layer
        self.revin = revin
        if self.revin:
            self.norm = ReversibleInstanceNorm1d(n_series=n_series)

        # Mixing layers
        mixing_layers = [
            MixingLayer(
                n_series=n_series, input_size=input_size, dropout=dropout, ff_dim=ff_dim
            )
            for _ in range(n_block)
        ]
        self.mixing_layers = nn.Sequential(*mixing_layers)

        # Linear output with Loss dependent dimensions
        self.out = nn.Linear(
            in_features=input_size, out_features=h * self.loss.outputsize_multiplier
        )

    def forward(self, windows_batch):
        # Parse batch
        x = windows_batch["insample_y"]  # x: [batch_size, input_size, n_series]
        batch_size = x.shape[0]

        # TSMixer: InstanceNorm + Mixing layers + Dense output layer + ReverseInstanceNorm
        if self.revin:
            x = self.norm(x)
        x = self.mixing_layers(x)
        x = x.permute(0, 2, 1)
        x = self.out(x)
        x = x.permute(0, 2, 1)
        if self.revin:
            x = self.norm.reverse(x)

        x = x.reshape(
            batch_size, self.h, self.loss.outputsize_multiplier * self.n_series
        )
        forecast = self.loss.domain_map(x)

        return forecast
