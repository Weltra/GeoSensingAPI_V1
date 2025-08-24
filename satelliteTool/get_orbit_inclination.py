from skyfield.api import EarthSatellite, load


def get_orbit_inclination(*args, multiInvocation: bool = False, times: int = 1):
    """

    :param args:
    :param multiInvocation:
    :param times:
    :return:
    """
    ts = load.timescale()

    def calculate_inclination(tle_data):
        """计算卫星的轨道倾角"""
        lines = tle_data.strip().split("\n")
        if len(lines) < 3:
            return "Invalid TLE data"

        # 解析TLE数据
        satellite = EarthSatellite(lines[1], lines[2], lines[0], ts)

        # 从TLE数据中提取轨道倾角
        inclination = satellite.model.inclo  # 轨道倾角 (degrees)

        return inclination

    if multiInvocation:
        if len(args) < times:
            return "Invalid number of arguments for multiInvocation"

        results = {}
        for i in range(times):
            tle_data = args[i]
            results[f"TLE_{i + 1}"] = calculate_inclination(tle_data)

        return results
    else:
        if len(args) < 1:
            return "Invalid number of arguments for single invocation"

        tle_data = args[0]
        return calculate_inclination(tle_data)
