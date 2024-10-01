from collections import defaultdict

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

    if volts > 54.5:
        soc = 100
        return soc
    elif 51.5 <= volts and volts <= 54.5:
        soc = (105.9668 / (1 + 2.718282**(-2.0705 * (volts - 52.493))))
    elif volts < 51.5:
        soc = (1.4473*volts - 58.4573)
    else:
        print(f"{volts} not in [0, 54.5]")

    return round(soc)

def volts_soc2json(i):
    volts = float(i/10)
    soc = socbyvolts(i)

    return f'{{"volts": "{volts}", "soc": "{soc}" }}'

