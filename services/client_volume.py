MIN_CLIENT_VOLUME_GB = 20.0


class ClientVolumeTooLowError(ValueError):
    def __init__(self, volume_gb: float) -> None:
        super().__init__(
            f"حداقل حجم سرویس {MIN_CLIENT_VOLUME_GB:g} GB است "
            f"(وارد شده: {volume_gb:g} GB)."
        )


def validate_client_volume_gb(volume_gb: float) -> None:
    if volume_gb < MIN_CLIENT_VOLUME_GB:
        raise ClientVolumeTooLowError(volume_gb)
