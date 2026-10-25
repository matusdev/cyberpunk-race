/*
 * Slow-motion director: big crashes, long jumps, close calls with oncoming traffic and the finish line
 * drop the simulation into slow motion for a moment. `amount` (0..1) drives the visual grade and the
 * music slow-down; `glitch` drives the impact glitch.
 */
import { damp } from '../core/math.ts';
import type { RaceEvent, Racer } from '../race/race.ts';
import type { VehicleBody } from '../vehicle/physics.ts';

export class SlowMo {
  scale = 1;
  amount = 0;
  glitch = 0;
  enabled = true;
  private target = 1;
  private hold = 0; // real seconds left
  private cooldown = 0;
  private airHold = 0;
  onStart: ((reason: string) => void) | null = null;

  trigger(scale: number, seconds: number, reason: string, glitch = 0) {
    if (!this.enabled) return;
    if (this.cooldown > 0 && reason !== 'finish') return;
    this.target = Math.min(this.target, scale);
    this.hold = Math.max(this.hold, seconds);
    this.glitch = Math.max(this.glitch, glitch);
    this.cooldown = reason === 'finish' ? 0 : 5;
    this.onStart?.(reason);
  }

  onEvent(e: RaceEvent, player: Racer) {
    if (e.type === 'impact' && e.racer === player && (e.with === 'traffic' || e.with === 'car') && e.dv > 10) this.trigger(0.28, 0.85, 'crash', 0.8);
    else if (e.type === 'impact' && e.racer === player && e.with === 'wall' && e.dv > 16) this.trigger(0.35, 0.6, 'crash', 0.6);
    else if (e.type === 'nearmiss' && e.oncoming && e.speed > 48) this.trigger(0.45, 0.42, 'nearmiss');
    else if (e.type === 'finish' && e.racer === player) {
      this.cooldown = 0;
      this.trigger(0.22, 2.4, 'finish', 0.3);
    }
  }

  update(realDt: number, b: VehicleBody, state: string) {
    this.cooldown = Math.max(0, this.cooldown - realDt);
    // airtime: once the player has been airborne for a moment at speed, hang in the air
    if (this.enabled && !b.onGround && b.air > 0.28 && b.speed > 30 && state === 'racing') {
      if (this.airHold === 0) this.onStart?.('air');
      this.airHold += realDt;
      if (this.airHold < 1.6) {
        this.target = Math.min(this.target, 0.38);
        this.hold = Math.max(this.hold, 0.05);
      }
    } else if (b.onGround) this.airHold = 0;
    if (this.hold > 0) this.hold -= realDt;
    else this.target = 1;
    this.scale = damp(this.scale, this.target, this.target < this.scale ? 14 : 3.2, realDt);
    this.amount = Math.max(0, Math.min(1, (1 - this.scale) / 0.7));
    this.glitch = damp(this.glitch, 0, 5, realDt);
  }

  reset() {
    this.scale = this.target = 1;
    this.amount = this.glitch = this.hold = this.cooldown = this.airHold = 0;
  }
}
