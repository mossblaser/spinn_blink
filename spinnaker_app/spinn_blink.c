/**
 * A SpiNNaker app which will drive the LED attached to the chip it lives on
 * with a PWM pattern whose duty cycle is given by the value in the first word
 * of SDRAM.
 */

#include "spinnaker.h"
#include "spin1_api.h"

#define BLINK_LED 0

#define MIN(a,b) (((a)<(b)) ? (a) : (b))
#define MAX(a,b) (((a)<(b)) ? (b) : (a))

const volatile uint *led_value = SDRAM_BASE_UNBUF;

uint counter = 0;

void
on_timer_tick(uint _1, uint _2)
{
	counter += 1;
	counter &= 0xFF;
	
	if (counter <= (*led_value)) {
		spin1_led_control(LED_ON(BLINK_LED));
	} else {
		spin1_led_control(LED_OFF(BLINK_LED));
	}
}


void
c_main()
{
	// Set up timer to tick once per ms
	spin1_set_timer_tick(10);
	spin1_callback_on(TIMER_TICK, on_timer_tick, 3);
	
	// Go!
	spin1_start();
}
