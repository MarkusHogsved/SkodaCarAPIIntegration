# Skoda Car API

Home Assistant integration for the official [MyŠkoda Public API](https://public.api.connect.skoda-auto.cz/docs).

It uses the API key you create in the MyŠkoda app. There is no account login and no reverse-engineered app traffic, and it runs fine next to other Škoda integrations.

## Features

- **Battery and charging:** battery level, range, charging power and rate, charging state, AC/DC, time to full, cable connected and cable lock, and whether the car is at a saved charging location
- **Charging control:** start/stop switch, charging limit (50–100 % in steps of 10) and charge mode
- **Climate:** air conditioning switch with a configurable target temperature. Active ventilation and auxiliary heating are available where the vehicle supports them.
- **Vehicle:** lock, doors, windows, trunk, bonnet, sunroof, lights, odometer, and parking position as a device tracker
- **Combustion and hybrid:** fuel level, total range, AdBlue range
- **API housekeeping:** key expiry date, remaining request quota, and a repair notice one week before the key expires

Entities are created only for the data your vehicle reports, and controls only for the operations it supports.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/MarkusHogsved/SkodaCarAPIIntegration` as type **Integration**.
2. Install **Skoda Car API** and restart Home Assistant.

### Manual

Copy `custom_components/skoda_car_api` into your Home Assistant `config/custom_components/` folder and restart.

## Setup

1. In the MyŠkoda app, create an API key and select the vehicles it should cover ([direct link](https://go.skoda.eu/api-keys), which opens in the app).
2. In Home Assistant go to **Settings → Devices & services → Add integration → Skoda Car API**.
3. Paste the key and enter the VIN. Add the integration once per vehicle.

### Renewing the key

API keys expire. The **API key expires** sensor shows the date, and a repair notice appears seven days before. Create a new key in the app, then open the integration and choose **Reconfigure** to paste it. If the key has already expired, Home Assistant asks for a new one automatically.

## Polling and the request quota

The API allows **20 requests per hour per vehicle**. Commands count against the same quota, and so do failed requests. The integration adapts to this:

| Situation | Default interval |
|---|---|
| Charging cable connected | 6 min |
| Otherwise | 20 min |
| Remaining quota at or below the reserve (default 4) | Wait until the quota window resets |
| `429 Too Many Requests` | Wait for `Retry-After` |

About 90 seconds after a command is accepted, the integration reads the state back once, so the result shows up without waiting for the next poll. Until then, the control shows the requested value.

Intervals and the command reserve can be changed under **Configure**. The **Refresh** button polls immediately and uses one request.

The data reflects what the vehicle last sent to Škoda's backend; **Charging data from vehicle** shows when that was. A faster poll interval will not make the vehicle report more often.

## Actions

| Action | Purpose |
|---|---|
| `skoda_car_api.start_air_conditioning` | Start climate with an explicit temperature and battery-power setting |
| `skoda_car_api.start_auxiliary_heating` | Start the auxiliary heater (requires S-PIN) |
| `skoda_car_api.stop_auxiliary_heating` | Stop the auxiliary heater |

Example: precondition the cabin before departure

```yaml
action: skoda_car_api.start_air_conditioning
data:
  device_id: <your vehicle>
  temperature: 21
  without_external_power: false
```

## Troubleshooting

- **Entities unavailable after setup:** check **Settings → System → Repairs** and the integration's diagnostics download. The diagnostics redact VIN, plate and position.
- **"Request quota used up":** the quota is per vehicle, so another tool using the API for the same car shares it. Lower the poll rate or raise the reserve under **Configure**.
- **"The vehicle declined the request":** the car limits how often it accepts remote commands and may refuse them when its battery is low. Try again later.

Debug logging:

```yaml
logger:
  logs:
    custom_components.skoda_car_api: debug
```

## Disclaimer

This is a community project and is not affiliated with or endorsed by Škoda Auto. Škoda is a trademark of Škoda Auto a.s.
