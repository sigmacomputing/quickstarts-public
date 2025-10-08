import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { LocationStrategy, PathLocationStrategy } from '@angular/common';

import { providePrimeNG } from 'primeng/config';
import Aura from '@primeuix/themes/aura';
import { definePreset } from '@primeuix/themes';

import { routes } from './app.routes';

const SigmaPreset = definePreset(Aura, {
    semantic: {
        colorScheme: {
            light: {
                surface: {
                    200: 'rgba(255, 201, 100, 0.7)'
                }
            }
        }
    }
});

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }), 
    provideRouter(routes), 
    provideHttpClient(),
    { provide: LocationStrategy, useClass: PathLocationStrategy },
    providePrimeNG({ theme: { preset: SigmaPreset } })
  ]
};
