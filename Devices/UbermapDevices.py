import os.path
from Ubermap.configobj import ConfigObj
from functools import partial
import hashlib
import re
from Ubermap.UbermapLibs import log, log_call, config


class UbermapDevices:
    PARAMS_PER_BANK = 8
    SECTION_BANKS = 'Banks'
    SECTION_PARAMETER_VALUES = 'ParameterValues'
    SECTION_PARAMETER_VALUE_TYPES = 'ParameterValueTypes'
    SECTION_CONFIG = 'Config'

    device_config_cache = {}

    regex = re.compile(r"^\d+\_", re.IGNORECASE)

    def __init__(self):
        self.cfg = config.load('devices')
        log.info('UbermapDevices ready')

    def get_attributes(self, obj):
        from inspect import getmembers
        from types import FunctionType

        def attributes(obj):
            disallowed_names = {
                name for name, value in getmembers(type(obj))
                if isinstance(value, FunctionType)
            }

            for name in (x for x in dir(obj) if 'drum_pads' not in x):
                log.debug(name)
                log.debug(name + '=' + str(getattr(obj, name)))

            return {
                name + '=' + str(getattr(obj, name))
                for name in dir(obj)
                if name[0] != '_'
                and (not name.endswith("listener"))
                and 'drum_pads' not in name
                and name not in disallowed_names
                and hasattr(obj, name)
            }

        return attributes(obj)

    def get_device_name(self, device):
        if not device:
            return None

        # ignore other device types for now
        if not device.class_name == 'PluginDevice':
            return None

        log.debug("class_display_name: " + (device.class_display_name or '')
                 + ", class_name: " + (device.class_name or '') + ", name: " + (device.name or ''))

        if hasattr(device, 'class_display_name'):
            device_name = device.class_display_name
        else:
            device_name = device.class_name

        if not device_name:
            return None

        # if isinstance(device_name, type(None)):
        #     log.debug(";".join(a for a in self.get_attributes(device)))

        strict_matching_mode = self.cfg.get('Strict_matching', device_name)
        if strict_matching_mode == 'NAME':
            return device_name + '_' + device.name
        elif strict_matching_mode == 'PARAMETERS':
            params = ''
            for parameter_name in sorted(map(lambda p: p.original_name, device.parameters[1:])):
                params += '.' + parameter_name
            return device_name + '_' + hashlib.md5(params.encode('UTF-8')).hexdigest()
        else:
            return device_name

    def get_device_filename(self, device, folder, extension):
        name = self.get_device_name(device)
        return config.get_path(name, folder) + "." + extension

    def dump_device(self, device, config_exists, used_parameters=set()):
        if not device:
            return

        device_name = self.get_device_name(device)

        if not device_name:
            return

        log.debug('device: ' + self.get_device_name(device) + ', config exists: ' + str(config_exists)
                  + ', dump new devices: ' + str(self.cfg.get('Dump', 'new_devices')) + ', dump unmapped: '
                  + str(self.cfg.get('Dump', 'unmapped_parameters')))

        if config_exists and self.cfg.get('Dump', 'unmapped_parameters') == 'True':
            self.dump_as_unmapped_properties(device, used_parameters)
        elif (not config_exists) and self.cfg.get('Dump', 'new_devices') == 'True':
            self.dump_as_config(device, self.cfg.get('Dump', 'default_ignore') == 'True')

        log.debug('dumped device: ' + self.get_device_name(device))

    def dump_as_unmapped_properties(self, device, used_parameters):
        os.makedirs(config.get_path('Unmapped'), exist_ok=True)

        unmapped_parameters = sorted([i.original_name for i in device.parameters[1:]
                                      if i.original_name not in used_parameters])

        log.debug('dumping device: ' + self.get_device_name(device) + "; used parameters count: "
                  + str(len(used_parameters)) + "; unmapped parameters count: " + str(len(unmapped_parameters)))

        file_path = self.get_device_filename(device, "Unmapped", "txt")
        if len(unmapped_parameters) > 0:
            with open(file_path, 'w+') as f:
                for parameter in unmapped_parameters:
                    f.write("%s\n" % parameter)
        else:
            if os.path.isfile(file_path):
                os.remove(file_path)

    def dump_as_config(self, device, ignore):
        filepath = self.get_device_filename(device, "Devices", "cfg")
        if self.get_device_config(device) or os.path.isfile(filepath):
            log.debug('not dumping device: ' + self.get_device_name(device))
            return False

        log.debug('dumping device: ' + self.get_device_name(device))

        config = ConfigObj()
        config.filename = filepath

        config[self.SECTION_BANKS] = {}
        config[self.SECTION_PARAMETER_VALUES] = {}
        config[self.SECTION_PARAMETER_VALUE_TYPES] = {}

        config[self.SECTION_CONFIG] = {}
        config[self.SECTION_CONFIG]['Cache'] = False
        config[self.SECTION_CONFIG]['Ignore'] = ignore

        count = 0
        bank = 1
        for parameter_name in sorted(map(lambda p: p.original_name, device.parameters[1:])):
            if count == 0:
                section = 'Bank ' + str(bank)
                config[self.SECTION_BANKS][section] = {}
                bank = bank + 1

            config[self.SECTION_BANKS][section][parameter_name] = parameter_name

            count = count + 1
            if count == self.PARAMS_PER_BANK:
                count = 0

        config.write()

    def get_device_config(self, device):
        local_device_name = self.get_device_name(device)

        if local_device_name is None or len(local_device_name) == 0:
            return False

        log.debug("Device name is " + local_device_name)

        cfg = config.load_device_config(local_device_name)

        if not cfg:
            return False

        return cfg if cfg.get('Config', 'Ignore') == 'False' else False

    def get_custom_device_banks(self, device):
        device_config = self.get_device_config(device)

        if not device_config:
            log.debug("Devices.get_custom_device_banks: config not found for " + str(self.get_device_name(device)))
            self.dump_device(device, False)
            return False

        log.debug("Devices.get_custom_device_banks: config found for " + str(self.get_device_name(device)))
        banks = device_config.get(self.SECTION_BANKS)
        bank_keys = device_config.get(self.SECTION_BANKS).keys()

        mapped_params = set([re.sub(self.regex, '', p)
                            for bank in bank_keys if banks.get(bank) is not None
                            for p in banks.get(bank)])

        self.dump_device(device, True, mapped_params)

        # is_addition_mode = self.cfg.get('Additional_banks', self.get_device_name(device)) == 'True'
        #
        # if is_addition_mode:
        #     original_banks.extend(bank_keys)
        #     return original_banks

        return bank_keys

    def get_custom_device_params(self, device, bank_name=None):
        if not bank_name:
            bank_name = self.SECTION_BANKS

        device_config = self.get_device_config(device)

        if not device_config:
            return False

        def parse_custom_parameter_values(values):
            # Split the values on || to see if we have custom value start points specified
            values_split = [x.split("||") for x in values]
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

        def get_parameter_by_name(device, name_mapping):
            count = 0
            for device_parameter in device.parameters:
                original_name = name_mapping[0]
                if (original_name == device_parameter.original_name) \
                        or (original_name == str(count) + "_" + device_parameter.original_name) \
                        or re.match("^\\d+_\\w+$" + device_parameter.original_name, original_name):

                    if not name_mapping[1]:
                        custom_name = original_name
                    elif name_mapping[1] == "*":
                        # this line just splits words by case: SomeWord -> Some Word
                        custom_name = " ".join(re.sub('([A-Z][a-z]+)', r' \1', re.sub('([A-Z]+)', r' \1', original_name)).split())
                    else:
                        custom_name = name_mapping[1]

                    device_parameter.custom_name = custom_name

                    [device_parameter.custom_parameter_values, device_parameter.custom_parameter_start_points] = \
                        get_custom_parameter_values(name_mapping[0])

                    return device_parameter
                count = count + 1

        def names_to_params(bank):
            return map(partial(get_parameter_by_name, device), bank.items())

        ret = map(names_to_params, device_config.get(bank_name).values())
        return ret
