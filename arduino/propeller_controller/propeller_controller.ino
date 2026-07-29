#include <Servo.h>

// propeller_app wiring:
// - Hobbywing ESC PWM signal: Arduino D11
// - Hobbywing ESC signal ground: Arduino GND
// - RPM sensor is connected directly to NI USB-6001 PFI0, not Arduino.
constexpr byte ESC_SIGNAL_PIN = 11;

// XRotor Pro H60A throttle range used by this test stand.
constexpr int ESC_MIN_PULSE_US = 1100;
constexpr int ESC_MAX_PULSE_US = 1940;
constexpr int STOP_COMMAND_PERCENT = 10;
constexpr int MAX_COMMAND_PERCENT = 95;

Servo esc;

void writeEscPercent(int percent) {
  percent = constrain(
      percent,
      STOP_COMMAND_PERCENT,
      MAX_COMMAND_PERCENT
  );

  if (percent == STOP_COMMAND_PERCENT) {
    esc.writeMicroseconds(ESC_MIN_PULSE_US);
    return;
  }

  const int pulseUs = map(
      percent,
      STOP_COMMAND_PERCENT,
      MAX_COMMAND_PERCENT,
      ESC_MIN_PULSE_US,
      ESC_MAX_PULSE_US
  );
  esc.writeMicroseconds(pulseUs);
}

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(50);

  esc.attach(ESC_SIGNAL_PIN);
  writeEscPercent(STOP_COMMAND_PERCENT);

  // Keep minimum throttle during ESC initialization.
  delay(3000);
}

void loop() {
  if (Serial.available() <= 0) {
    return;
  }

  const int requestedPercent = Serial.parseInt();
  while (Serial.available() > 0) {
    Serial.read();
  }

  if (
      requestedPercent >= STOP_COMMAND_PERCENT &&
      requestedPercent <= MAX_COMMAND_PERCENT
  ) {
    writeEscPercent(requestedPercent);
  }
}
