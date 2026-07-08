import { Component, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-privacy-policy-page',
  standalone: true,
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="min-h-screen bg-white px-6 py-12 lg:px-16">
      <div class="mx-auto max-w-3xl">
        <!-- Header -->
        <div class="mb-8">
          <a routerLink="/" class="mb-6 inline-flex items-center gap-2 text-sm text-emerald-600 hover:underline">
            &larr; Back to ModishLog
          </a>
          <h1 class="mt-4 text-3xl font-bold text-gray-900">Privacy Policy</h1>
          <p class="mt-2 text-sm text-gray-500">Effective date: 8 July 2026 &nbsp;·&nbsp; Last updated: 8 July 2026</p>
        </div>

        <div class="prose prose-gray max-w-none text-sm text-gray-700 leading-relaxed space-y-6">

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">1. Who we are</h2>
            <p>
              ModishLog ("we", "us", "our") is a business management platform designed for traders
              and small-business owners. This Privacy Policy explains how we collect, use, and
              protect your personal data in accordance with the Nigeria Data Protection Regulation
              (NDPR) 2019 and the NDPR Implementation Framework 2020.
            </p>
            <p class="mt-2">
              Data Controller: ModishLog · Email:
              <a href="mailto:privacy&#64;modishlog.com" class="text-emerald-600 hover:underline">privacy&#64;modishlog.com</a>
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">2. Data we collect</h2>
            <ul class="list-disc pl-5 space-y-1">
              <li><strong>Account data</strong> — full name, email address, hashed password.</li>
              <li><strong>Business data</strong> — business name, country, city, phone, timezone, tax number, fiscal year.</li>
              <li><strong>Transaction data</strong> — sales, purchases, inventory records, expenses you enter.</li>
              <li><strong>Usage data</strong> — login timestamps, session tokens (stored as HttpOnly cookies), failed login counts.</li>
              <li><strong>Consent record</strong> — the date and time you accepted this policy.</li>
            </ul>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">3. Why we collect it (lawful basis)</h2>
            <ul class="list-disc pl-5 space-y-1">
              <li><strong>Contract performance</strong> — to provide the ModishLog service you signed up for.</li>
              <li><strong>Legitimate interest</strong> — to secure accounts (rate limiting, lockout), detect abuse, and improve the platform.</li>
              <li><strong>Consent</strong> — to send product updates or marketing emails (you may withdraw at any time).</li>
              <li><strong>Legal obligation</strong> — to retain records required by Nigerian tax and business regulations.</li>
            </ul>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">4. How we store and protect your data</h2>
            <p>
              Your data is stored on servers in the European Union (Hetzner Cloud) and backed up
              daily. We use TLS encryption in transit and AES-256 encryption at rest. Passwords are
              hashed with bcrypt and are never stored in plain text. Access to production data is
              restricted to authorised personnel only.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">5. Data sharing</h2>
            <p>We do <strong>not</strong> sell your personal data. We share data only with:</p>
            <ul class="list-disc pl-5 space-y-1">
              <li>Sub-processors required to run the platform (hosting, monitoring) bound by data-processing agreements.</li>
              <li>Regulatory authorities if required by law.</li>
            </ul>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">6. Retention</h2>
            <p>
              We retain your account and business data for as long as your account is active, plus
              7 years after closure (to meet Nigerian financial-record requirements). You may
              request earlier deletion where no legal obligation applies.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">7. Your rights under the NDPR</h2>
            <ul class="list-disc pl-5 space-y-1">
              <li><strong>Access</strong> — request a copy of your personal data.</li>
              <li><strong>Correction</strong> — ask us to correct inaccurate data.</li>
              <li><strong>Erasure</strong> — request deletion of your data (subject to legal retention obligations).</li>
              <li><strong>Portability</strong> — receive your data in a structured, machine-readable format.</li>
              <li><strong>Withdraw consent</strong> — for any processing based solely on consent, you may withdraw at any time without affecting prior lawful processing.</li>
              <li><strong>Lodge a complaint</strong> — with the Nigeria Data Protection Commission (NDPC) at <a href="https://ndpc.gov.ng" target="_blank" rel="noopener noreferrer" class="text-emerald-600 hover:underline">ndpc.gov.ng</a>.</li>
            </ul>
            <p class="mt-2">
              To exercise any right, email
              <a href="mailto:privacy&#64;modishlog.com" class="text-emerald-600 hover:underline">privacy&#64;modishlog.com</a>.
              We respond within 30 days.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">8. Cookies</h2>
            <p>
              We use strictly necessary HttpOnly cookies for authentication (access token, refresh
              token). No third-party tracking or advertising cookies are set.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">9. Changes to this policy</h2>
            <p>
              We will notify registered users by email at least 30 days before any material change.
              Continued use after the effective date constitutes acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">10. Contact</h2>
            <p>
              ModishLog Data Protection Officer ·
              <a href="mailto:privacy&#64;modishlog.com" class="text-emerald-600 hover:underline">privacy&#64;modishlog.com</a>
            </p>
          </section>

        </div>
      </div>
    </div>
  `,
})
export class PrivacyPolicyPageComponent {}
