from pydantic import BaseModel, Field
from typing import List, Dict
from decimal import Decimal
import os
import yaml
from dotenv import load_dotenv
from .core.exceptions import ConfigError

class EnvConfig(BaseModel):
    api_key_env: str = "MEXC_API_KEY"
    api_secret_env: str = "MEXC_API_SECRET"
    base_url_env: str = "MEXC_BASE_URL"
    recv_window_env: str = "MEXC_RECV_WINDOW"

class RuntimeConfig(BaseModel):
    poll_seconds: int = 30
    log_level: str = "INFO"

class SafetyConfig(BaseModel):
    allow_symbols: List[str] = Field(default_factory=list)
    max_usdt_per_order: Decimal = Decimal("50")
    min_usdt_per_order: Decimal = Decimal("5")
    cooldown_seconds: int = 1800
    dry_run_default: bool = False

class ExecutionCfg(BaseModel):
    default_order_type: str = "MARKET"
    slippage_bps: int = 20
    limit_price_buffer_bps: int = 10
    time_in_force: str = "GTC"

class PortfolioCfg(BaseModel):
    quote_asset: str = "USDT"
    base_assets: List[str] = Field(default_factory=list)
    min_profit_sweep_usdt: Decimal = Decimal("2.0")
    profit_sweep_to_base: Dict[str, str] = Field(default_factory=dict)

class StrategyCfg(BaseModel):
    name: str
    params: dict = Field(default_factory=dict)

class AppConfig(BaseModel):
    env: EnvConfig = EnvConfig()
    runtime: RuntimeConfig = RuntimeConfig()
    safety: SafetyConfig = SafetyConfig()
    execution: ExecutionCfg = ExecutionCfg()
    portfolio: PortfolioCfg = PortfolioCfg()
    strategy: StrategyCfg

def load_config(path: str) -> AppConfig:
    load_dotenv()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cfg = AppConfig.model_validate(data)

    api_key = os.getenv(cfg.env.api_key_env)
    api_secret = os.getenv(cfg.env.api_secret_env)
    if not api_key or not api_secret:
        raise ConfigError("Missing API key/secret in .env")
    return cfg
