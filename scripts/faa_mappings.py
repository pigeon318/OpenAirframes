TYPE_REGISTRANT = {
    "1": "individual",
    "2": "partnership",
    "3": "corporation",
    "4": "co_owned",
    "5": "government",
    "7": "llc",
    "8": "non_citizen_corporation",
    "9": "non_citizen_co_owned",
}

TYPE_AIRCRAFT = {
    "1": "glider",
    "2": "balloon",
    "3": "blimp_dirigible",
    "4": "fixed_wing_single_engine",
    "5": "fixed_wing_multi_engine",
    "6": "rotorcraft",
    "7": "weight_shift_control",
    "8": "powered_parachute",
    "9": "gyroplane",
    "H": "hybrid_lift",
    "O": "other",
}

TYPE_ENGINE = {
    "0": "none",
    "1": "reciprocating",
    "2": "turbo_prop",
    "3": "turbo_shaft",
    "4": "turbo_jet",
    "5": "turbo_fan",
    "6": "ramjet",
    "7": "two_cycle",
    "8": "four_cycle",
    "9": "unknown",
    "10": "electric",
    "11": "rotary",
}

STATUS = {
    "V": "valid",
    "T": "valid",
    "M": "valid",
    "D": "expired",
    "13": "expired",
    "27": "expired",
    "E": "revoked",
    "9": "revoked",
    "R": "pending",
    "2": "pending",
    "3": "pending",
    "4": "pending",
    "Z": "reserved",
    "5": "reserved",
    "6": "cancelled",
    "18": "cancelled",
    "20": "cancelled",
    "22": "cancelled",
    "10": "cancellation_pending",
    "11": "cancellation_pending",
    "12": "cancellation_pending",
    "16": "cancellation_pending",
    "17": "cancellation_pending",
    "19": "cancellation_pending",
    "21": "cancellation_pending",
    "23": "cancellation_pending",
    "29": "cancellation_pending",
    "1": "notice_sent",
    "8": "notice_sent",
    "14": "notice_sent",
    "15": "notice_sent",
    "24": "notice_sent",
    "25": "notice_sent",
    "26": "notice_sent",
    "28": "notice_sent",
    "A": "other",
    "S": "other",
    "W": "other",
    "X": "other",
    "7": "other",
    "N": "other",
}

AIRCRAFT_CATEGORY = {
    "1": "land",
    "2": "sea",
    "3": "amphibian",
}

BUILDER_CERTIFICATION = {
    "0": "type_certificated",
    "1": "not_type_certificated",
    "2": "light_sport",
}

WEIGHT_CLASS = {
    "CLASS 1": "up_to_12499_lbs",
    "CLASS 2": "12500_to_19999_lbs",
    "CLASS 3": "20000_lbs_and_over",
    "CLASS 4": "uav_up_to_55_lbs",
}


def decode(mapping, code):
    code = (code or "").strip()
    if not code:
        return None
    return mapping.get(code)
