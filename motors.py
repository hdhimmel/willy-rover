import RPi.GPIO as GPIO
import time, config

class Motor:
    def __init__(self,in1,in2):
        self.in1=in1; self.in2=in2
        GPIO.setup(in1,GPIO.OUT); GPIO.setup(in2,GPIO.OUT)
        self._p1=GPIO.PWM(in1,config.MOTOR_PWM_FREQ)
        self._p2=GPIO.PWM(in2,config.MOTOR_PWM_FREQ)
        self._p1.start(0); self._p2.start(0)
    def drive(self,speed):
        speed=max(-config.SPEED_MAX,min(config.SPEED_MAX,speed)); d=abs(speed)*100
        if speed>0:   self._p1.ChangeDutyCycle(d);  self._p2.ChangeDutyCycle(0)
        elif speed<0: self._p1.ChangeDutyCycle(0);  self._p2.ChangeDutyCycle(d)
        else:         self._p1.ChangeDutyCycle(0);  self._p2.ChangeDutyCycle(0)
    def brake(self): self._p1.ChangeDutyCycle(100); self._p2.ChangeDutyCycle(100)
    def stop(self):  self._p1.ChangeDutyCycle(0);   self._p2.ChangeDutyCycle(0)
    def cleanup(self): self._p1.stop(); self._p2.stop()

class DriveBase:
    def __init__(self):
        GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
        self.lf=Motor(config.MOTOR_LF_IN1,config.MOTOR_LF_IN2)
        self.lm=Motor(config.MOTOR_LM_IN1,config.MOTOR_LM_IN2)
        self.lr=Motor(config.MOTOR_LR_IN1,config.MOTOR_LR_IN2)
        self.rf=Motor(config.MOTOR_RF_IN1,config.MOTOR_RF_IN2)
        self.rm=Motor(config.MOTOR_RM_IN1,config.MOTOR_RM_IN2)
        self.rr=Motor(config.MOTOR_RR_IN1,config.MOTOR_RR_IN2)
        self._L=[self.lf,self.lm,self.lr]; self._R=[self.rf,self.rm,self.rr]
        self._all=self._L+self._R; self.current_speed=0.0; self.stop()
    def _set(self,l,r): [m.drive(l) for m in self._L]; [m.drive(r) for m in self._R]
    def forward(self,speed=None):
        s=speed or config.SPEED_ROAM; self.current_speed=s; self._set(s,s)
    def reverse(self,speed=None):
        s=speed or config.SPEED_SLOW; self.current_speed=-s; self._set(-s,-s)
    def turn_left(self,speed=None):
        s=speed or config.SPEED_TURN; self._set(-s,s)
    def turn_right(self,speed=None):
        s=speed or config.SPEED_TURN; self._set(s,-s)
    def stop(self): [m.stop() for m in self._all]; self.current_speed=0.0
    def brake(self): [m.brake() for m in self._all]; self.current_speed=0.0
    def forward_for(self,t,speed=None): self.forward(speed); time.sleep(t); self.stop()
    def reverse_for(self,t,speed=None): self.reverse(speed); time.sleep(t); self.stop()
    def turn_left_for(self,t,speed=None): self.turn_left(speed); time.sleep(t); self.stop()
    def turn_right_for(self,t,speed=None): self.turn_right(speed); time.sleep(t); self.stop()
    def cleanup(self): self.stop(); [m.cleanup() for m in self._all]; GPIO.cleanup()
