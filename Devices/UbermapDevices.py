import os.path
from configobj import ConfigObj
from functools import partial
import hashlib
from Ubermap.UbermapLibs import log, log_call, config

class UbermapDevices:
    PARAMS_PER_BANK = 8
    SECTION_BANKS = 'Banks'
    SECTION_PARAMETER_VALUES = 'ParameterValues'
    SECTION_PARAMETER_VALUE_TYPES = 'ParameterValueTypes'
    SECTION_CONFIG  = 'Config'

    device_config_cache = {}

    def __init__(self):
        self.cfg = config.load('devices')
        log.info('UbermapDevices ready')

    def get_device_name(self, device):
        if not device:
            return None

        name = device.class_display_name or device.class_name
        return name

    def get_device_filename(self, device):
        name = self.get_device_name(device)
        return config.get_path(name, 'Devices')

    def dump_device(self, device, used_parameters = set()):
        if not device:
            return

        folder = self.get_device_filename(device)

        if not os.path.exists(folder):
            os.makedirs(folder)

        file_path = folder + os.path.sep + "unmapped.txt"
        unmapped_parameters = sorted([i.original_name for i in device.parameters[1:] if i.original_name not in used_parameters])
        log.info('dumping device: ' + self.get_device_name(device))
        log.info("used parameters count: " + str(len(used_parameters)))
        log.info("unmapped parameters count: " + str(len(unmapped_parameters)))

        if len(unmapped_parameters) > 0:
            with open(file_path, 'w+') as f:
                for parameter in unmapped_parameters:
                    f.write("%s\n" % parameter)
        else:
            if os.path.isfile(file_path):
                os.remove(file_path)

        log.info('dumped device: ' + self.get_device_name(device))

    def get_device_config(self, device):
        local_device_name = self.get_device_name(device)

        if local_device_name is None or len(local_device_name) == 0:
            return False

        cfg = config.load("banks", subdir='Devices', subdir2=local_device_name)

        if not cfg:
            return False

        return cfg if cfg.get('Config', 'Ignore') == 'False' else False


    def get_custom_device_banks(self, device):
        device_config = self.get_device_config(device)
        if not device_config:
            self.dump_device(device)
            return False

        banks = device_config.get(self.SECTION_BANKS).keys()
        used_params = set([p for bank in banks if device_config.get(self.SECTION_BANKS).get(bank) is not None for p in device_config.get(self.SECTION_BANKS).get(bank)])
        self.dump_device(device, used_params)
        return banks

    def get_custom_device_params(self, device, bank_name = None):
        if not bank_name:
            bank_name = self.SECTION_BANKS

        device_config = self.get_device_config(device)

        if not device_config:
            return False

        def parse_custom_parameter_values(values):
            # Split the values on || to see if we have custom value start points specified
            values_split = map(lambda s: s.split('||'), values)
            has_value_start_points = all(len(x) == 2 for x in values_split)
            if not has_value_start_points:
                return [values, None]

            return [[x[0] for x in values_split], [float(x[1]) for x in values_split]]

        def get_custom_parameter_values(parameter_name):
            values = device_config.get(self.SECTION_PARAMETER_VALUES, parameter_name)
            if not values:
                return [None, None]

            # If we have an array, i.e. comma separated list, just use that
            if isinstance(values, list):
                return parse_custom_parameter_values(values)

            # Otherwise try and look up the string key in ParameterValueTypes and use that
            values_type = device_config.get(self.SECTION_PARAMETER_VALUE_TYPES, values)
            if values_type:
                return parse_custom_parameter_values(values_type)

        def get_parameter_by_name(device, nameMapping):
            count = 0
            for i in device.parameters:
                if (nameMapping[0] == str(count) + "_" + i.original_name) or (nameMapping[0] == i.original_name):
                    log.debug("got " + nameMapping[1] + " for " + nameMapping[0])
                    i.custom_name = nameMapping[1]

                    [i.custom_parameter_values, i.custom_parameter_start_points] = get_custom_parameter_values(nameMapping[0])

                    return i
                count = count + 1

        def names_to_params(bank):
            return map(partial(get_parameter_by_name, device), bank.items())

        ret = map(names_to_params, device_config.get(bank_name).values())
        return ret
