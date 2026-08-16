import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# §P2 "Configuration cleanup" of the 2026-08-08 external code audit: config.py is large enough
# now that a duplicate address or an out-of-order threshold is a real, easy-to-miss risk.
# config.validate() is pure (reads module globals, no hardware) -- tests monkeypatch those
# globals to simulate a bad config and confirm each check actually fires.

def test_validate_current_config_is_clean():
    # BAT_FULL_V was 11.39 (below BAT_WARN_V=11.4) from 2026-08-08 until fixed 2026-08-16 --
    # owner measured the real post-fuse full-charge voltage (11.58V) and it's now above every
    # threshold. This test documents current real state, not a hypothetical -- if it starts
    # failing, something in the live config regressed; don't just update the assertion to match.
    assert config.validate()==[]

def test_validate_detects_duplicate_i2c_address(monkeypatch):
    monkeypatch.setattr(config,'ARM_PCA_ADDR',config.STEER_PCA_ADDR)
    problems=config.validate()
    assert any('duplicate I2C address' in p for p in problems)

def test_validate_detects_duplicate_gpio_pin(monkeypatch):
    monkeypatch.setattr(config,'SONAR_LEFT_TRIG',config.SONAR_FRONT_TRIG)
    problems=config.validate()
    assert any('duplicate GPIO pin' in p for p in problems)

def test_validate_detects_mcp23017_pin_collision(monkeypatch):
    # ENCODER_PINS['lr'] uses bank B bits 0,1 -> MCP pin index 8. Colliding IMU_RST_MCP_PIN with
    # it should be caught even though it's a completely different chip *role* (reset line vs
    # encoder), since they'd fight over the same physical MCP23017 pin.
    monkeypatch.setattr(config,'IMU_RST_MCP_PIN',8)
    problems=config.validate()
    assert any('IMU_RST_MCP_PIN' in p and 'collides' in p for p in problems)

def test_validate_detects_out_of_order_battery_tiers(monkeypatch):
    monkeypatch.setattr(config,'BAT_SAFE_V',config.BAT_RTH_V+1.0)  # SAFE now above RTH -- wrong
    problems=config.validate()
    assert any('not strictly ordered' in p for p in problems)

def test_validate_detects_non_positive_hysteresis(monkeypatch):
    monkeypatch.setattr(config,'BAT_HYSTERESIS_V',0.0)
    problems=config.validate()
    assert any('BAT_HYSTERESIS_V' in p for p in problems)

def test_validate_detects_tilt_warn_at_or_above_limit(monkeypatch):
    monkeypatch.setattr(config,'IMU_TILT_WARN',config.IMU_TILT_LIMIT)
    problems=config.validate()
    assert any('IMU_TILT_WARN' in p for p in problems)

def test_validate_detects_bad_servo_range(monkeypatch):
    monkeypatch.setattr(config,'SERVO_CENTER_US',config.SERVO_MAX_US+100)  # center outside range
    problems=config.validate()
    assert any('SERVO pulse-width range' in p for p in problems)

def test_validate_detects_speed_above_max(monkeypatch):
    monkeypatch.setattr(config,'SPEED_ROAM',config.SPEED_MAX+0.1)
    problems=config.validate()
    assert any('SPEED_ROAM' in p for p in problems)

def test_validate_detects_non_positive_command_duration(monkeypatch):
    monkeypatch.setattr(config,'MAX_COMMAND_DURATION_S',0.0)
    problems=config.validate()
    assert any('MAX_COMMAND_DURATION_S' in p for p in problems)

def test_validate_clean_when_bat_full_v_fixed(monkeypatch):
    # Proves the checks are independent -- fixing the one known issue should leave zero problems,
    # not mask/reveal something else.
    monkeypatch.setattr(config,'BAT_FULL_V',config.BAT_WARN_V)
    assert config.validate()==[]
