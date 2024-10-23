from collections import defaultdict
import logging

int2on_off_dict= defaultdict(lambda:"unknown", {0:"off", 1:"on"})

def int2on_off(i):
    return int2on_off_dict[i]

def divideby10(i):
    return float(i)/10

def mv2v(i):
    volts = float(i)*.001
    return f"{volts:.3f}"

def floatnegation(i):
    # We don't want a negative sign on 0
    current = 0.0 if i == 0.0 else -i
    return f"{current:.2f}"

def float2decimals(i):
    #just return the number with 2 decimal places
    return f"{i:.2f}"

def byte2relays(i):
    FLAG_PRECHARGE   = 0x10    # Pre-charge relay
    FLAG_HEATING     = 0x20    # Heating relay
    FLAG_FANRELAY    = 0x40    # Fan Relay
    FLAG_CUSTOM8     = 0x80    # Custom-8 Relay
    FLAG_DISCHARGE   = 0x01    # Discharge Relay
    FLAG_TTLNEGATIVE = 0x02    # Total Negative Relay
    FLAG_SLOWCHARGE  = 0x04    # Slow-charge relay
    FLAG_FAST        = 0x08    # Fast Relay

    relayjson = str(
        f'{{"Pre-Charge": "{"on" if i & FLAG_PRECHARGE else "off"}", '
        f'"Heating": "{"on" if i & FLAG_HEATING else "off"}", '
        f'"Fan": "{"on" if i & FLAG_FANRELAY else "off"}", '
        f'"Custom-8": "{"on" if i & FLAG_CUSTOM8 else "off"}", '
        f'"Discharge": "{"on" if i & FLAG_DISCHARGE else "off"}", '
        f'"Total Negative": "{"on" if i & FLAG_TTLNEGATIVE else "off"}", '
        f'"Slow-Charge": "{"on" if i & FLAG_SLOWCHARGE else "off"}", '
        f'"Fast": "{"on" if i & FLAG_FAST else "off"}"}}')

    return relayjson

def val2celsius(i):
    """
    The Renogy BMS doesn't send temperature as a regualr value.
    It is stored as (tempC + 400) * 10
    """
    return str((i - 400) / 10)

def val2workmodel(i):
    match i:
        case 1:
            return "Slow Charge Mode"
        case 2:
            return "Fast Charge Mode"
        case 3:
            return "Discharge Mode"
        case 4:
            return "Power-Up Mode"
        case 5:
            return "Power-Down Mode"

    return "Unknown"

def val2chargestatus(i):
    match i:
        case 0:
            return "Stop Charging"
        case 1:
            return "Charging"
        case 2:
            return "Charging Failure"
        case 3:
            return "Charging Failure"

    return "Unknown"

def bytetominorpatch(i):
    """
     Converts a single byte to minor.patch version.
     Convert byte to hex and split the number to make minor and patch version
    """
    version = f"{i:x}"

    return f"{version[0]}.{version[1]}"

def socbyvolts(i):
    #convert volts(passed as volts*10) to SOC as determined by volts instead of BMS reported
    ''' Example:
    Voltage SOC (Capacity)
    54.4V 100% (Resting)
    53.6V 99%
    53.2V 90%
    52.8V 70%
    52.4V 40%
    52.0V 30%
    51.6V 20%
    51.2V 17%
    50.0V 14%
    48.0V 9%
    40.0V 0%
    '''
    volts = float(i/10)
    soc = 0

    # From https://github.com/ascv/socRenogyLiFePO4

    if 54.4 < volts and volts <= 58.4:
        soc = 100
    # Use a logistic function at the top end
    elif 52.4 <= volts and volts <= 54.4:
        L = 101.191451
        x0 = 52.537895
        k = 3.16037696
        soc = L / (1 + 2.718282**(-k * (volts - x0)))
        soc = soc if soc < 100 else 100 # ensure we don't get values above 100
    # Use a linear function in the middle
    elif 51.6 <= volts and volts < 52.4:
        soc = 25*volts - 1270
    # Use a logistic function at the bottom end
    elif 40 < volts < 51.6:
        soc = 1.4473*volts - 58.457263
        L = 36.440261
        x0 = 51.29112
        k = 0.3567057
        soc = L / (1 + 2.718282**(-k * (volts - x0)))
    # Handle slightly lower voltages not seen in the training data
    elif 38 < volts and volts <= 40:
        soc = 0
    else:
        print(f"{volts} not in [0, 56.4]")
        return soc

    return round(soc)

def usablesocbyvolts(i):
    #convert volts(passed as volts*10) to usable SOC as determined by volts instead of BMS reported
    volts = float(i/10)
    soc = 0

    # From https://github.com/ascv/socRenogyLiFePO4

    if 53.2 <= volts:
        soc = 100
    elif 51.6 <= volts and volts < 53.2:
        soc = (volts - 51.515) / 0.017
    # Use a logistic function at the bottom end
    elif 51.2 <= volts < 51.6:
        soc = (volts - 51.2) / 0.08
    # Handle slightly lower voltages not seen in the training data
    elif volts < 51.2:
        soc = 0
    else:
        print(f"{volts} not in [0, 53.2]")
        return soc

    return round(soc)

def volts_soc2json(i):
    volts = float(i/10)
    soc = socbyvolts(i)
    usablesoc = usablesocbyvolts(i)

    return f'{{"volts": "{volts}", "soc": "{soc}", "usablesoc": "{usablesoc}"}}'

