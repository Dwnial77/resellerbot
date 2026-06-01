def expiry_label(days: int) -> str:
    return f"{days} روز" if days > 0 else "نامحدود"


def suggest_template_name(volume_gb: float, expiry_days: int) -> str:
    if volume_gb == int(volume_gb):
        vol_s = str(int(volume_gb))
    else:
        vol_s = str(volume_gb).rstrip("0").rstrip(".")
    if expiry_days <= 0:
        return f"{vol_s}GB/نامحدود"
    return f"{vol_s}GB/{expiry_days}روز"
