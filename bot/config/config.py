from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int
    API_HASH: str

    REF_ID: str = '0001b3Lf'
    
    FAKE_USERAGENT: bool = True
    POINTS_COUNT: list[int] = [450, 550]
    AUTO_PLAY_GAME: bool = False
    AUTO_TASK: bool = False
    AUTO_DAILY_REWARD: bool = False
    AUTO_CLAIM_STARS: bool = False
    AUTO_CLAIM_COMBO: bool = False
    AUTO_RANK_UPGRADE: bool = False
    AUTO_RAFFLE: bool = False
    AUTO_CHANGE_NAME: bool = False
    AUTO_ADD_WALLET: bool = False

    USE_RANDOM_DELAY_IN_RUN: bool = True
    RANDOM_DELAY_IN_RUN: list[int] = [0, 15]

    USE_PROXY_FROM_FILE: bool = False


settings = Settings()

