import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface CheckoutResponse {
  authorization_url: string;
  access_code: string;
  reference: string;
}

@Injectable({ providedIn: 'root' })
export class BillingService {
  private readonly api = inject(ApiService);

  /** Initiate a Paystack hosted checkout for the given tier (task #238's
   * POST /billing/checkout). Caller redirects the browser to
   * response.authorization_url. */
  initiateCheckout(tier: 'basic' | 'pro'): Observable<CheckoutResponse> {
    return this.api.post<CheckoutResponse>('/billing/checkout', { tier });
  }
}
