# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/models.mamba.ipynb.

# %% auto 0
__all__ = ['PositionalEmbedding', 'TokenEmbedding', 'TimeFeatureEmbedding', 'FixedEmbedding', 'TemporalEmbedding',
           'DataEmbedding', 'ResidualBlock', 'MambaBlock', 'RMSNorm', 'Mamba']

# %% ../../nbs/models.mamba.ipynb 7
import math
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange, repeat, einsum

from ..losses.pytorch import MAE
from ..common._base_windows import BaseWindows

# %% ../../nbs/models.mamba.ipynb 9
class PositionalEmbedding(nn.Module):
    def __init__(self, d_model, max_len=5000):
        super(PositionalEmbedding, self).__init__()
        # Compute the positional encodings once in log space.
        pe = torch.zeros(max_len, d_model).float()
        pe.require_grad = False

        position = torch.arange(0, max_len).float().unsqueeze(1)
        div_term = (
            torch.arange(0, d_model, 2).float() * -(math.log(10000.0) / d_model)
        ).exp()

        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)

        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x):
        return self.pe[:, : x.size(1)]


class TokenEmbedding(nn.Module):
    def __init__(self, c_in, d_model):
        super(TokenEmbedding, self).__init__()
        padding = 1 if torch.__version__ >= "1.5.0" else 2
        self.tokenConv = nn.Conv1d(
            in_channels=c_in,
            out_channels=d_model,
            kernel_size=3,
            padding=padding,
            padding_mode="circular",
            bias=False,
        )
        for m in self.modules():
            if isinstance(m, nn.Conv1d):
                nn.init.kaiming_normal_(
                    m.weight, mode="fan_in", nonlinearity="leaky_relu"
                )

    def forward(self, x):
        x = self.tokenConv(x.permute(0, 2, 1)).transpose(1, 2)
        return x


class TimeFeatureEmbedding(nn.Module):
    def __init__(self, d_model, embed_type="timeF", freq="h"):
        super(TimeFeatureEmbedding, self).__init__()

        freq_map = {"h": 4, "t": 5, "s": 6, "m": 1, "a": 1, "w": 2, "d": 3, "b": 3}
        d_inp = freq_map[freq]
        self.embed = nn.Linear(d_inp, d_model, bias=False)

    def forward(self, x):
        return self.embed(x)


class FixedEmbedding(nn.Module):
    def __init__(self, c_in, d_model):
        super(FixedEmbedding, self).__init__()

        w = torch.zeros(c_in, d_model).float()
        w.require_grad = False

        position = torch.arange(0, c_in).float().unsqueeze(1)
        div_term = (
            torch.arange(0, d_model, 2).float() * -(math.log(10000.0) / d_model)
        ).exp()

        w[:, 0::2] = torch.sin(position * div_term)
        w[:, 1::2] = torch.cos(position * div_term)

        self.emb = nn.Embedding(c_in, d_model)
        self.emb.weight = nn.Parameter(w, requires_grad=False)

    def forward(self, x):
        return self.emb(x).detach()


class TemporalEmbedding(nn.Module):
    def __init__(self, d_model, embed_type="fixed", freq="h"):
        super(TemporalEmbedding, self).__init__()

        minute_size = 4
        hour_size = 24
        weekday_size = 7
        day_size = 32
        month_size = 13

        Embed = FixedEmbedding if embed_type == "fixed" else nn.Embedding
        if freq == "t":
            self.minute_embed = Embed(minute_size, d_model)
        self.hour_embed = Embed(hour_size, d_model)
        self.weekday_embed = Embed(weekday_size, d_model)
        self.day_embed = Embed(day_size, d_model)
        self.month_embed = Embed(month_size, d_model)

    def forward(self, x):
        x = x.long()
        minute_x = (
            self.minute_embed(x[:, :, 4]) if hasattr(self, "minute_embed") else 0.0
        )
        hour_x = self.hour_embed(x[:, :, 3])
        weekday_x = self.weekday_embed(x[:, :, 2])
        day_x = self.day_embed(x[:, :, 1])
        month_x = self.month_embed(x[:, :, 0])

        return hour_x + weekday_x + day_x + month_x + minute_x


class DataEmbedding(nn.Module):
    def __init__(self, c_in, d_model, embed_type="fixed", freq="h", dropout=0.1):
        super(DataEmbedding, self).__init__()

        self.value_embedding = TokenEmbedding(c_in=c_in, d_model=d_model)
        self.position_embedding = PositionalEmbedding(d_model=d_model)
        self.temporal_embedding = (
            TemporalEmbedding(d_model=d_model, embed_type=embed_type, freq=freq)
            if embed_type != "timeF"
            else TimeFeatureEmbedding(d_model=d_model, embed_type=embed_type, freq=freq)
        )
        self.dropout = nn.Dropout(p=dropout)

    def forward(self, x, x_mark):
        if x_mark is None:
            x = self.value_embedding(x) + self.position_embedding(x)
        else:
            x = (
                self.value_embedding(x)
                + self.temporal_embedding(x_mark)
                + self.position_embedding(x)
            )
        return self.dropout(x)

# %% ../../nbs/models.mamba.ipynb 11
class ResidualBlock(nn.Module):
    def __init__(self, d_model, d_inner, dt_rank):
        super(ResidualBlock, self).__init__()

        self.d_model = d_model
        self.mixer = MambaBlock(d_model, d_inner, dt_rank)
        self.norm = RMSNorm(self.d_model)

    def forward(self, x):
        output = self.mixer(self.norm(x)) + x
        return output


class MambaBlock(nn.Module):
    def __init__(
        self,
        d_model,
        d_inner,
        dt_rank,
        d_conv: int = 32,
        d_ff: int = 2048,
    ):
        super(MambaBlock, self).__init__()

        self.d_model = d_model
        self.d_conv = d_conv
        self.d_ff = d_ff
        self.d_inner = d_inner
        self.dt_rank = dt_rank

        self.in_proj = nn.Linear(self.d_model, self.d_inner * 2, bias=False)

        self.conv1d = nn.Conv1d(
            in_channels=self.d_inner,
            out_channels=self.d_inner,
            bias=True,
            kernel_size=self.d_conv,
            padding=self.d_conv - 1,
            groups=self.d_inner,
        )

        # takes in x and outputs the input-specific delta, B, C
        self.x_proj = nn.Linear(self.d_inner, self.dt_rank + self.d_ff * 2, bias=False)

        # projects delta
        self.dt_proj = nn.Linear(self.dt_rank, self.d_inner, bias=True)

        A = repeat(torch.arange(1, self.d_ff + 1), "n -> d n", d=self.d_inner)
        self.A_log = nn.Parameter(torch.log(A))
        self.D = nn.Parameter(torch.ones(self.d_inner))

        self.out_proj = nn.Linear(self.d_inner, self.d_model, bias=False)

    def forward(self, x):
        """
        Figure 3 in Section 3.4 in the paper
        """
        (b, l, d) = x.shape

        x_and_res = self.in_proj(x)  # [B, L, 2 * d_inner]
        (x, res) = x_and_res.split(split_size=[self.d_inner, self.d_inner], dim=-1)

        x = rearrange(x, "b l d -> b d l")
        x = self.conv1d(x)[:, :, :l]
        x = rearrange(x, "b d l -> b l d")

        x = F.silu(x)

        y = self.ssm(x)
        y = y * F.silu(res)

        output = self.out_proj(y)
        return output

    def ssm(self, x):
        """
        Algorithm 2 in Section 3.2 in the paper
        """

        (d_in, n) = self.A_log.shape

        A = -torch.exp(self.A_log.float())  # [d_in, n]
        D = self.D.float()  # [d_in]

        x_dbl = self.x_proj(x)  # [B, L, d_rank + 2 * d_ff]
        (delta, B, C) = x_dbl.split(
            split_size=[self.dt_rank, n, n], dim=-1
        )  # delta: [B, L, d_rank]; B, C: [B, L, n]
        delta = F.softplus(self.dt_proj(delta))  # [B, L, d_in]
        y = self.selective_scan(x, delta, A, B, C, D)

        return y

    def selective_scan(self, u, delta, A, B, C, D):
        (b, l, d_in) = u.shape
        n = A.shape[1]

        deltaA = torch.exp(
            einsum(delta, A, "b l d, d n -> b l d n")
        )  # A is discretized using zero-order hold (ZOH) discretization
        deltaB_u = einsum(
            delta, B, u, "b l d, b l n, b l d -> b l d n"
        )  # B is discretized using a simplified Euler discretization instead of ZOH. From a discussion with authors: "A is the more important term and the performance doesn't change much with the simplification on B"

        # selective scan, sequential instead of parallel
        x = torch.zeros((b, d_in, n), device=deltaA.device)
        ys = []
        for i in range(l):
            x = deltaA[:, i] * x + deltaB_u[:, i]
            y = einsum(x, C[:, i, :], "b d n, b n -> b d")
            ys.append(y)

        y = torch.stack(ys, dim=1)  # [B, L, d_in]
        y = y + u * D

        return y


class RMSNorm(nn.Module):
    def __init__(self, d_model, eps=1e-5):
        super(RMSNorm, self).__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(d_model))

    def forward(self, x):
        output = (
            x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps) * self.weight
        )
        return output

# %% ../../nbs/models.mamba.ipynb 13
class Mamba(BaseWindows):
    """
    Mamba

    TODO: docstring
    """

    # Class attributes
    SAMPLING_TYPE = "windows"
    EXOGENOUS_FUTR = False
    EXOGENOUS_HIST = False
    EXOGENOUS_STAT = False

    def __init__(
        self,
        h: int,
        input_size: int,
        encoding_freq: str,
        futr_exog_list=None,
        hist_exog_list=None,
        stat_exog_list=None,
        hidden_size: int = 512,  # d_model
        expand_factor: int = 2,  # expand
        embedding_type: str = "fixed",
        dropout: float = 0.05,
        e_layers: int = 2,
        loss=MAE(),
        valid_loss=None,
        max_steps: int = 5000,
        learning_rate: float = 1e-4,
        num_lr_decays: int = -1,
        early_stop_patience_steps: int = -1,
        val_check_steps: int = 100,
        batch_size: int = 32,
        valid_batch_size: Optional[int] = None,
        windows_batch_size=1024,
        inference_windows_batch_size: int = 1024,
        start_padding_enabled=False,
        step_size: int = 1,
        scaler_type: str = "identity",
        random_seed: int = 1,
        num_workers_loader: int = 0,
        drop_last_loader: bool = False,
        optimizer=None,
        optimizer_kwargs=None,
        **trainer_kwargs
    ):

        super(Mamba, self).__init__(
            h=h,
            input_size=input_size,
            hist_exog_list=hist_exog_list,
            stat_exog_list=stat_exog_list,
            futr_exog_list=futr_exog_list,
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
            num_workers_loader=num_workers_loader,
            drop_last_loader=drop_last_loader,
            random_seed=random_seed,
            optimizer=optimizer,
            optimizer_kwargs=optimizer_kwargs,
            **trainer_kwargs
        )

        self.hidden_size = hidden_size
        self.expand_factor = expand_factor
        self.encoding_freq = encoding_freq
        self.d_inner = self.hidden_size * expand_factor
        self.dt_rank = math.ceil(self.hidden_size / 16)
        self.embedding_type = embedding_type
        self.dropout = dropout
        self.e_layers = e_layers
        self.enc_in = 1
        self.c_out = 1

        self.embedding = DataEmbedding(
            self.enc_in,
            self.hidden_size,
            self.embedding_type,
            self.encoding_freq,
            self.dropout,
        )

        self.layers = nn.ModuleList(
            [
                ResidualBlock(self.hidden_size, self.d_inner, self.dt_rank)
                for _ in range(self.e_layers)
            ]
        )
        self.norm = RMSNorm(self.hidden_size)

        self.out_layer = nn.Linear(self.hidden_size, self.c_out, bias=False)

    def forecast(self, x_enc, x_mark_enc):
        mean_enc = x_enc.mean(1, keepdim=True).detach()
        x_enc = x_enc - mean_enc
        std_enc = torch.sqrt(
            torch.var(x_enc, dim=1, keepdim=True, unbiased=False) + 1e-5
        ).detach()
        x_enc = x_enc / std_enc

        x = self.embedding(x_enc, x_mark_enc)
        for layer in self.layers:
            x = layer(x)

        x = self.norm(x)
        x_out = self.out_layer(x)

        x_out = x_out * std_enc + mean_enc
        return x_out

    def forward(self, windows_batch):

        x_mark_enc = None  # use this for future exog

        insample_y = windows_batch["insample_y"]
        insample_y = insample_y.unsqueeze(-1)  # [Ws,L,1]

        y_pred = self.forecast(insample_y, x_mark_enc)
        y_pred = y_pred[:, -self.h :, :]
        y_pred = self.loss.domain_map(y_pred)

        return y_pred
