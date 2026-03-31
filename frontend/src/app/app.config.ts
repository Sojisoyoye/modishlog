import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { providePrimeNG } from 'primeng/config';
import { MessageService, ConfirmationService } from 'primeng/api';
import Aura from '@primeng/themes/aura';
import { definePreset } from '@primeng/themes';

import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { errorInterceptor } from './core/interceptors/error.interceptor';

const ModishPreset = definePreset(Aura, {
  semantic: {
    primary: {
      50: '#EBF2F8',
      100: '#C4D9EA',
      200: '#9DC0DC',
      300: '#5F99C6',
      400: '#2E75B6',
      500: '#1F4E79',
      600: '#1A4267',
      700: '#153656',
      800: '#102A44',
      900: '#0B1E33',
      950: '#071322',
    },
  },
});

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
    provideAnimationsAsync(),
    providePrimeNG({
      theme: {
        preset: ModishPreset,
        options: {
          darkModeSelector: false,
        },
      },
      ripple: true,
    }),
    MessageService,
    ConfirmationService,
  ],
};
