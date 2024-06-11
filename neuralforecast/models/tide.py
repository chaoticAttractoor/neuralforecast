# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/models.tide.ipynb.

# %% auto 0
__all__ = ['TiDE']

# %% ../../nbs/models.tide.ipynb 5
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from ..losses.pytorch import MAE
from ..common._base_model import BaseModel

# %% ../../nbs/models.tide.ipynb 8
class MLPResidual(nn.Module):
    def __init__(self, input_dim, hidden_size, output_dim, dropout, layernorm):
        super().__init__()
        self.layernorm = layernorm
        if layernorm:
            self.norm = nn.LayerNorm(output_dim)

        self.drop = nn.Dropout(dropout)
        self.lin1 = nn.Linear(input_dim, hidden_size)
        self.lin2 = nn.Linear(hidden_size, output_dim)
        self.skip = nn.Linear(input_dim, output_dim)

    def forward(self, input):
        # MLP dense
        x = F.relu(self.lin1(input))
        x = self.lin2(x)
        x = self.drop(x)

        # Skip connection
        x_skip = self.skip(input)

        # Combine
        x = x + x_skip

        if self.layernorm:
            return self.norm(x)

        return x

# %% ../../nbs/models.tide.ipynb 10
class TiDE(BaseModel):
    """TiDE

    Time-series Dense Encoder (`TiDE`) is a MLP-based univariate time-series forecasting model. `TiDE` uses Multi-layer Perceptrons (MLPs) in an encoder-decoder model for long-term time-series forecasting.

    **Parameters:**<br>
    `h`: int, forecast horizon.<br>
    `input_size`: int, considered autorregresive inputs (lags), y=[1,2,3,4] input_size=2 -> lags=[1,2].<br>
    `hidden_size`: int=1024, number of units for the dense MLPs.<br>
    `decoder_output_dim`: int=32, number of units for the output of the decoder.<br>
    `temporal_decoder_dim`: int=128, number of units for the hidden sizeof the temporal decoder.<br>
    `dropout`: float=0.0, dropout rate between (0, 1) .<br>
    `layernorm`: bool=True, if True uses Layer Normalization on the MLP residual block outputs.<br>
    `num_encoder_layers`: int=1, number of encoder layers.<br>
    `num_decoder_layers`: int=1, number of decoder layers.<br>
    `temporal_width`: int=4, lower temporal projected dimension.<br>
    `futr_exog_list`: str list, future exogenous columns.<br>
    `hist_exog_list`: str list, historic exogenous columns.<br>
    `stat_exog_list`: str list, static exogenous columns.<br>
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
    - [Das, Abhimanyu, Weihao Kong, Andrew Leach, Shaan Mathur, Rajat Sen, and Rose Yu (2024). "Long-term Forecasting with TiDE: Time-series Dense Encoder."](http://arxiv.org/abs/2304.08424)

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
        h,
        input_size,
        hidden_size=512,
        decoder_output_dim=32,
        temporal_decoder_dim=128,
        dropout=0.3,
        layernorm=True,
        num_encoder_layers=1,
        num_decoder_layers=1,
        temporal_width=4,
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

        # Inherit BaseWindows class
        super(TiDE, self).__init__(
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
        self.h = h

        if self.hist_exog_size > 0 or self.futr_exog_size > 0:
            self.hist_exog_projection = MLPResidual(
                input_dim=self.hist_exog_size,
                hidden_size=hidden_size,
                output_dim=temporal_width,
                dropout=dropout,
                layernorm=layernorm,
            )
        if self.futr_exog_size > 0:
            self.futr_exog_projection = MLPResidual(
                input_dim=self.futr_exog_size,
                hidden_size=hidden_size,
                output_dim=temporal_width,
                dropout=dropout,
                layernorm=layernorm,
            )

        # Encoder
        dense_encoder_input_size = (
            input_size
            + input_size * (self.hist_exog_size > 0) * temporal_width
            + (input_size + h) * (self.futr_exog_size > 0) * temporal_width
            + (self.stat_exog_size > 0) * self.stat_exog_size
        )

        dense_encoder_layers = [
            MLPResidual(
                input_dim=dense_encoder_input_size if i == 0 else hidden_size,
                hidden_size=hidden_size,
                output_dim=hidden_size,
                dropout=dropout,
                layernorm=layernorm,
            )
            for i in range(num_encoder_layers)
        ]
        self.dense_encoder = nn.Sequential(*dense_encoder_layers)

        # Decoder
        decoder_output_size = decoder_output_dim * h
        dense_decoder_layers = [
            MLPResidual(
                input_dim=hidden_size,
                hidden_size=hidden_size,
                output_dim=(
                    decoder_output_size if i == num_decoder_layers - 1 else hidden_size
                ),
                dropout=dropout,
                layernorm=layernorm,
            )
            for i in range(num_decoder_layers)
        ]
        self.dense_decoder = nn.Sequential(*dense_decoder_layers)

        # Temporal decoder with loss dependent dimensions
        self.temporal_decoder = MLPResidual(
            input_dim=decoder_output_dim + (self.futr_exog_size > 0) * temporal_width,
            hidden_size=temporal_decoder_dim,
            output_dim=self.loss.outputsize_multiplier,
            dropout=dropout,
            layernorm=layernorm,
        )

        # Global skip connection
        self.global_skip = nn.Linear(
            in_features=input_size, out_features=h * self.loss.outputsize_multiplier
        )

    def forward(self, windows_batch):
        # Parse windows_batch
        x = windows_batch["insample_y"]  #   [B, L, 1]
        hist_exog = windows_batch["hist_exog"]  #   [B, L, X]
        futr_exog = windows_batch["futr_exog"]  #   [B, L + h, F]
        stat_exog = windows_batch["stat_exog"]  #   [B, S]
        batch_size, seq_len = x.shape[:2]  #   B = batch_size, L = seq_len

        # Flatten insample_y
        x = x.reshape(batch_size, -1)  #   [B, L, 1] -> [B, L]

        # Global skip connection
        x_skip = self.global_skip(x)  #   [B, L] -> [B, h * n_outputs]
        x_skip = x_skip.reshape(
            batch_size, self.h, -1
        )  #   [B, h * n_outputs] -> [B, h, n_outputs]

        # Concatenate x with flattened historical exogenous
        if self.hist_exog_size > 0:
            x_hist_exog = self.hist_exog_projection(
                hist_exog
            )  #   [B, L, X] -> [B, L, temporal_width]
            x_hist_exog = x_hist_exog.reshape(
                batch_size, -1
            )  #   [B, L, temporal_width] -> [B, L * temporal_width]
            x = torch.cat(
                (x, x_hist_exog), dim=1
            )  #   [B, L] + [B, L * temporal_width] -> [B, L * (1 + temporal_width)]

        # Concatenate x with flattened future exogenous
        if self.futr_exog_size > 0:
            x_futr_exog = self.futr_exog_projection(
                futr_exog
            )  #   [B, L + h, F] -> [B, L + h, temporal_width]
            x_futr_exog_flat = x_futr_exog.reshape(
                batch_size, -1
            )  #   [B, L + h, temporal_width] -> [B, (L + h) * temporal_width]
            x = torch.cat(
                (x, x_futr_exog_flat), dim=1
            )  #   [B, L * (1 + temporal_width)] + [B, (L + h) * temporal_width] -> [B, L * (1 + 2 * temporal_width) + h * temporal_width]

        # Concatenate x with static exogenous
        if self.stat_exog_size > 0:
            x = torch.cat(
                (x, stat_exog), dim=1
            )  #   [B, L * (1 + 2 * temporal_width) + h * temporal_width] + [B, S] -> [B, L * (1 + 2 * temporal_width) + h * temporal_width + S]

        # Dense encoder
        x = self.dense_encoder(
            x
        )  #   [B, L * (1 + 2 * temporal_width) + h * temporal_width + S] -> [B, hidden_size]

        # Dense decoder
        x = self.dense_decoder(x)  #   [B, hidden_size] ->  [B, decoder_output_dim * h]
        x = x.reshape(
            batch_size, self.h, -1
        )  #   [B, decoder_output_dim * h] -> [B, h, decoder_output_dim]

        # Stack with futr_exog for horizon part of futr_exog
        if self.futr_exog_size > 0:
            x_futr_exog_h = x_futr_exog[
                :, seq_len:
            ]  #  [B, L + h, temporal_width] -> [B, h, temporal_width]
            x = torch.cat(
                (x, x_futr_exog_h), dim=2
            )  #  [B, h, decoder_output_dim] + [B, h, temporal_width] -> [B, h, temporal_width + decoder_output_dim]

        # Temporal decoder
        x = self.temporal_decoder(
            x
        )  #  [B, h, temporal_width + decoder_output_dim] -> [B, h, n_outputs]

        forecast = x + x_skip

        return forecast
