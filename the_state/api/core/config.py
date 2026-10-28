from payments import PaymentMode
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://state:state@localhost:5432/the_state",
        validation_alias=AliasChoices("THE_STATE_DATABASE_URL", "DATABASE_URL"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379",
        validation_alias=AliasChoices("THE_STATE_REDIS_URL", "REDIS_URL"),
    )

    openfema_base_url: str = Field(
        default="https://www.fema.gov/api/open/v2",
        validation_alias=AliasChoices(
            "THE_STATE_OPENFEMA_BASE_URL",
            "OPENFEMA_BASE_URL",
        ),
    )
    noaa_base_url: str = Field(
        default="https://api.weather.gov",
        validation_alias=AliasChoices("THE_STATE_NOAA_BASE_URL", "NOAA_BASE_URL"),
    )

    # Payment config. Only /decisions/evaluate is gated in v0.
    payment_mode: PaymentMode = Field(
        default="disabled",
        validation_alias=AliasChoices("THE_STATE_PAYMENT_MODE", "PAYMENT_MODE"),
    )
    payment_mock_token: str = Field(
        default="mock-paid",
        validation_alias=AliasChoices(
            "THE_STATE_PAYMENT_MOCK_TOKEN",
            "PAYMENT_MOCK_TOKEN",
        ),
    )
    x402_wallet_address: str = Field(
        default="",
        validation_alias=AliasChoices(
            "THE_STATE_X402_WALLET_ADDRESS",
            "X402_WALLET_ADDRESS",
        ),
    )
    x402_network: str = Field(
        default="eip155:84532",
        validation_alias=AliasChoices("THE_STATE_X402_NETWORK", "X402_NETWORK"),
    )
    x402_price_usd: float = Field(
        default=0.01,
        validation_alias=AliasChoices("THE_STATE_X402_PRICE_USD", "X402_PRICE_USD"),
    )
    x402_facilitator_url: str = Field(
        default="https://x402.org/facilitator",
        validation_alias=AliasChoices(
            "THE_STATE_X402_FACILITATOR_URL",
            "X402_FACILITATOR_URL",
        ),
    )

    debug: bool = Field(default=False, validation_alias="THE_STATE_DEBUG")


settings = Settings()
