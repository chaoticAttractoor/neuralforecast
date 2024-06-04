# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/models.bitcn.ipynb.

# %% auto 0
__all__ = ['CustomConv1d', 'TCNCell', 'BiTCN']

# %% ../../nbs/models.bitcn.ipynb 6
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

from ..losses.pytorch import MAE
from ..common._base_model import BaseModel

# %% ../../nbs/models.bitcn.ipynb 8
class CustomConv1d(nn.Module):
    def __init__(
        self,
        in_channels,
        out_channels,
        kernel_size,
        padding=0,
        dilation=1,
        mode="backward",
        groups=1,
    ):
        super().__init__()
        k = np.sqrt(1 / (in_channels * kernel_size))
        weight_data = -k + 2 * k * torch.rand(
            (out_channels, in_channels // groups, kernel_size)
        )
        bias_data = -k + 2 * k * torch.rand((out_channels))
        self.weight = nn.Parameter(weight_data, requires_grad=True)
        self.bias = nn.Parameter(bias_data, requires_grad=True)
        self.dilation = dilation
        self.groups = groups
        if mode == "backward":
            self.padding_left = padding
            self.padding_right = 0
        elif mode == "forward":
            self.padding_left = 0
            self.padding_right = padding

    def forward(self, x):
        xp = F.pad(x, (self.padding_left, self.padding_right))
        return F.conv1d(
            xp, self.weight, self.bias, dilation=self.dilation, groups=self.groups
        )


class TCNCell(nn.Module):
    def __init__(
        self,
        in_channels,
        out_channels,
        kernel_size,
        padding,
        dilation,
        mode,
        groups,
        dropout,
    ):
        super().__init__()
        self.conv1 = CustomConv1d(
            in_channels, out_channels, kernel_size, padding, dilation, mode, groups
        )
        self.conv2 = CustomConv1d(out_channels, in_channels * 2, 1)
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        h_prev, out_prev = x
        h = self.drop(F.gelu(self.conv1(h_prev)))
        h_next, out_next = self.conv2(h).chunk(2, 1)
        return (h_prev + h_next, out_prev + out_next)

# %% ../../nbs/models.bitcn.ipynb 10
class BiTCN(BaseModel):
    """BiTCN

    Bidirectional Temporal Convolutional Network (BiTCN) is a forecasting architecture based on two temporal convolutional networks (TCNs). The first network ('forward') encodes future covariates of the time series, whereas the second network ('backward') encodes past observations and covariates. This is a univariate model.

    **Parameters:**<br>
    `h`: int, forecast horizon.<br>
    `input_size`: int, considered autorregresive inputs (lags), y=[1,2,3,4] input_size=2 -> lags=[1,2].<br>
    `hidden_size`: int=16, units for the TCN's hidden state size.<br>
    `dropout`: float=0.1, dropout rate used for the dropout layers throughout the architecture.<br>
    `futr_exog_list`: str list, future exogenous columns.<br>
    `hist_exog_list`: str list, historic exogenous columns.<br>
    `stat_exog_list`: str list, static exogenous columns.<br>
    `exclude_insample_y`: bool=False, the model skips the autoregressive features y[t-input_size:t] if True.<br>
    `loss`: PyTorch module, instantiated train loss class from [losses collection](https://nixtla.github.io/neuralforecast/losses.pytorch.html).<br>
    `valid_loss`: PyTorch module=`loss`, instantiated valid loss class from [losses collection](https://nixtla.github.io/neuralforecast/losses.pytorch.html).<br>
    `max_steps`: int=1000, maximum number of training steps.<br>
    `learning_rate`: float=1e-3, Learning rate between (0, 1).<br>
    `num_lr_decays`: int=-1, Number of learning rate decays, evenly distributed across max_steps.<br>
    `early_stop_patience_steps`: int=-1, Number of validation iterations before early stopping.<br>
    `val_check_steps`: int=100, Number of training steps between every validation loss check.<br>
    `batch_size`: int=32, number of different series in each batch.<br>
    `valid_batch_size`: int=None, number of different series in each validation and test batch, if None uses batch_size.<br>
    `windows_batch_size`: int=1024, number of windows to sample in each training batch, default uses all.<br>
    `inference_windows_batch_size`: int=-1, number of windows to sample in each inference batch, -1 uses all.<br>
    `start_padding_enabled`: bool=False, if True, the model will pad the time series with zeros at the beginning, by input size.<br>
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

    """

    # Class attributes
    EXOGENOUS_FUTR = True
    EXOGENOUS_HIST = True
    EXOGENOUS_STAT = True
    MULTIVARIATE = False  # If the model produces multivariate forecasts (True) or univariate (False)
    RECURRENT = (
        False  # If the model produces forecasts recursively (True) or direct (False)
    )

    def __init__(
        self,
        h: int,
        input_size: int,
        hidden_size: int = 16,
        dropout: float = 0.5,
        futr_exog_list=None,
        hist_exog_list=None,
        stat_exog_list=None,
        exclude_insample_y=False,
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
        super(BiTCN, self).__init__(
            h=h,
            input_size=input_size,
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

        # ----------------------------------- Parse dimensions -----------------------------------#
        # TCN
        kernel_size = 2  # Not really necessary as parameter, so simplifying the architecture here.
        self.kernel_size = kernel_size
        self.hidden_size = hidden_size
        self.h = h
        self.input_size = input_size
        self.dropout = dropout

        # Calculate required number of TCN layers based on the required receptive field of the TCN
        self.n_layers_bwd = int(
            np.ceil(np.log2(((self.input_size - 1) / (self.kernel_size - 1)) + 1))
        )

        # ---------------------------------- Instantiate Model -----------------------------------#

        # Dense layers
        self.lin_hist = nn.Linear(
            1 + self.hist_exog_size + self.stat_exog_size + self.futr_exog_size,
            hidden_size,
        )
        self.drop_hist = nn.Dropout(dropout)

        # TCN looking back
        layers_bwd = [
            TCNCell(
                hidden_size,
                hidden_size,
                kernel_size,
                padding=(kernel_size - 1) * 2**i,
                dilation=2**i,
                mode="backward",
                groups=1,
                dropout=dropout,
            )
            for i in range(self.n_layers_bwd)
        ]
        self.net_bwd = nn.Sequential(*layers_bwd)

        # TCN looking forward when future covariates exist
        output_lin_dim_multiplier = 1
        if self.futr_exog_size > 0:
            self.n_layers_fwd = int(
                np.ceil(
                    np.log2(
                        ((self.h + self.input_size - 1) / (self.kernel_size - 1)) + 1
                    )
                )
            )
            self.lin_futr = nn.Linear(self.futr_exog_size, hidden_size)
            self.drop_futr = nn.Dropout(dropout)
            layers_fwd = [
                TCNCell(
                    hidden_size,
                    hidden_size,
                    kernel_size,
                    padding=(kernel_size - 1) * 2**i,
                    dilation=2**i,
                    mode="forward",
                    groups=1,
                    dropout=dropout,
                )
                for i in range(self.n_layers_fwd)
            ]
            self.net_fwd = nn.Sequential(*layers_fwd)
            output_lin_dim_multiplier += 2

        # Dense temporal and output layers
        self.drop_temporal = nn.Dropout(dropout)
        self.temporal_lin1 = nn.Linear(self.input_size, hidden_size)
        self.temporal_lin2 = nn.Linear(hidden_size, self.h)
        self.output_lin = nn.Linear(
            output_lin_dim_multiplier * hidden_size, self.loss.outputsize_multiplier
        )

    def forward(self, windows_batch):
        # Parse windows_batch
        x = windows_batch["insample_y"]  #   [B, L, 1]
        hist_exog = windows_batch["hist_exog"]  #   [B, L, X]
        futr_exog = windows_batch["futr_exog"]  #   [B, L + h, F]
        stat_exog = windows_batch["stat_exog"]  #   [B, S]

        # Concatenate x with historic exogenous
        batch_size, seq_len = x.shape[:2]  #   B = batch_size, L = seq_len
        if self.hist_exog_size > 0:
            x = torch.cat(
                (x, hist_exog), dim=2
            )  #   [B, L, 1] + [B, L, X] -> [B, L, 1 + X]

        # Concatenate x with static exogenous
        if self.stat_exog_size > 0:
            stat_exog = stat_exog.unsqueeze(1).repeat(
                1, seq_len, 1
            )  #   [B, S] -> [B, L, S]
            x = torch.cat(
                (x, stat_exog), dim=2
            )  #   [B, L, 1 + X] + [B, L, S] -> [B, L, 1 + X + S]

        # Concatenate x with future exogenous & apply forward TCN to x_futr
        if self.futr_exog_size > 0:
            x = torch.cat(
                (x, futr_exog[:, :seq_len]), dim=2
            )  #   [B, L, 1 + X + S] + [B, L, F] -> [B, L, 1 + X + S + F]
            x_futr = self.drop_futr(
                self.lin_futr(futr_exog)
            )  #   [B, L + h, F] -> [B, L + h, hidden_size]
            x_futr = x_futr.permute(
                0, 2, 1
            )  #   [B, L + h, hidden_size] -> [B, hidden_size, L + h]
            _, x_futr = self.net_fwd(
                (x_futr, 0)
            )  #   [B, hidden_size, L + h] -> [B, hidden_size, L + h]
            x_futr_L = x_futr[
                :, :, :seq_len
            ]  #   [B, hidden_size, L + h] -> [B, hidden_size, L]
            x_futr_h = x_futr[
                :, :, seq_len:
            ]  #   [B, hidden_size, L + h] -> [B, hidden_size, h]

        # Apply backward TCN to x
        x = self.drop_hist(
            self.lin_hist(x)
        )  #   [B, L, 1 + X + S + F] -> [B, L, hidden_size]
        x = x.permute(0, 2, 1)  #   [B, L, hidden_size] -> [B, hidden_size, L]
        _, x = self.net_bwd((x, 0))  #   [B, hidden_size, L] -> [B, hidden_size, L]

        # Concatenate with future exogenous for seq_len
        if self.futr_exog_size > 0:
            x = torch.cat(
                (x, x_futr_L), dim=1
            )  #   [B, hidden_size, L] + [B, hidden_size, L] -> [B, 2 * hidden_size, L]

        # Temporal dense layer to go to output horizon
        x = self.drop_temporal(
            F.gelu(self.temporal_lin1(x))
        )  #   [B, 2 * hidden_size, L] -> [B, 2 * hidden_size, hidden_size]
        x = self.temporal_lin2(
            x
        )  #   [B, 2 * hidden_size, hidden_size] -> [B, 2 * hidden_size, h]

        # Concatenate with future exogenous for horizon
        if self.futr_exog_size > 0:
            x = torch.cat(
                (x, x_futr_h), dim=1
            )  #   [B, 2 * hidden_size, h] + [B, hidden_size, h] -> [B, 3 * hidden_size, h]

        # Output layer to create forecasts
        x = x.permute(0, 2, 1)  #   [B, 3 * hidden_size, h] -> [B, h, 3 * hidden_size]
        forecast = self.output_lin(x)  #   [B, h, 3 * hidden_size] -> [B, h, n_outputs]

        return forecast
