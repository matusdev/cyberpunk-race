/*
 * NIGHT CITY RUSH — entry point.
 */
import './ui/styles.css';
import { Game } from './game/game.ts';

const game = new Game(document.getElementById('gl') as HTMLCanvasElement, document.getElementById('ui') as HTMLElement);
game.boot();
(window as unknown as { game: Game }).game = game;
