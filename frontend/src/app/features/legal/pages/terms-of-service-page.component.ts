import { Component, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-terms-of-service-page',
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
          <h1 class="mt-4 text-3xl font-bold text-gray-900">Terms of Service</h1>
          <p class="mt-2 text-sm text-gray-500">Effective date: 12 September 2026 &nbsp;·&nbsp; Last updated: 12 September 2026</p>
        </div>

        <div class="prose prose-gray max-w-none text-sm text-gray-700 leading-relaxed space-y-6">

          <section>
            <p>
              These Terms of Service ("<strong>Terms</strong>") govern your access to and use of
              ModishLog, a business-management platform for traders and small-business owners
              ("ModishLog", "we", "us", "our", the "<strong>Service</strong>"). By creating an
              account or otherwise using the Service, you agree to these Terms on behalf of
              yourself or the business you represent, and you confirm you have the authority to do
              so. You must be at least 18 years old to use the Service. If you do not agree to
              these Terms, please do not use the Service.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">1. Accounts</h2>
            <ul class="list-disc pl-5 space-y-1">
              <li><strong>Creating an account.</strong> When you register, you agree to provide accurate and complete information about yourself and your business, and to keep that information current.</li>
              <li><strong>Account security.</strong> You are responsible for keeping your login credentials confidential and for all activity that occurs under your account. If you believe your account has been accessed without authorization, contact us immediately at <a href="mailto:contact&#64;modishlog.com" class="text-emerald-600 hover:underline">contact&#64;modishlog.com</a>. We are not liable for losses resulting from your failure to keep your credentials secure.</li>
              <li><strong>One account per business.</strong> The owner who registers a business is responsible for managing access for any staff accounts created under it, including revoking access when a staff member leaves.</li>
            </ul>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">2. Using the Service</h2>
            <ul class="list-disc pl-5 space-y-1">
              <li><strong>License.</strong> Subject to these Terms, we grant you a limited, non-exclusive, non-transferable, revocable license to access and use the Service for your own business's internal operations.</li>
              <li><strong>Restrictions.</strong> You may not: (i) license, sell, rent, lease, or commercially exploit access to the Service itself; (ii) reverse-engineer, decompile, or attempt to extract the source code of the Service, except where applicable law gives you the right to do so; (iii) use the Service to build a competing product; (iv) upload data you don't have the right to share, or use the Service for any unlawful purpose; or (v) attempt to circumvent rate limits, security controls, or business-data isolation between accounts.</li>
              <li><strong>Changes to the Service.</strong> We may modify, add to, or discontinue features of the Service at any time. We'll make reasonable efforts to notify registered users of material changes that affect how they use the Service day-to-day.</li>
              <li><strong>Your data stays yours.</strong> You own the business data you enter into the Service (sales, inventory, customers, and similar records). We do not claim ownership of it. See our <a routerLink="/privacy" class="text-emerald-600 hover:underline">Privacy Policy</a> for how we handle it.</li>
              <li><strong>Our ownership.</strong> All intellectual property rights in the Service itself — its software, design, and underlying technology — belong to ModishLog. These Terms don't transfer any of those rights to you beyond the limited license above.</li>
              <li><strong>Feedback.</strong> If you share feedback or feature suggestions with us, you grant us a perpetual, royalty-free license to use that feedback to improve the Service, without any obligation to compensate or credit you.</li>
            </ul>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">3. AI-assisted features</h2>
            <p>
              Some parts of the Service (such as price suggestions and reorder recommendations) use
              statistical models and, in limited cases, third-party AI providers. These are
              decision-support tools, not financial or legal advice — you're responsible for
              reviewing and deciding whether to act on any suggestion the Service gives you.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">4. Fees</h2>
            <p>
              Where the Service or a plan requires payment, the price and billing terms will be
              presented to you before you're charged. We may change pricing for future billing
              periods with reasonable advance notice to registered users.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">5. Privacy and cookies</h2>
            <p>
              Your use of the Service is also governed by our
              <a routerLink="/privacy" class="text-emerald-600 hover:underline">Privacy Policy</a>,
              which explains what data we collect, why, and your rights under the Nigeria Data
              Protection Regulation (NDPR) — including the cookies the Service uses, which are
              limited to the two strictly-necessary session cookies described there. The Privacy
              Policy is incorporated into these Terms by reference.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">6. Third-party services</h2>
            <p>
              The Service integrates with third-party providers for things like transactional
              email, exchange-rate data, and payment/POS data import. We don't control those
              providers and aren't responsible for their availability or errors, though we choose
              them carefully and require data-handling commitments consistent with our Privacy
              Policy. Your use of any third-party service linked from or integrated with ModishLog
              is also subject to that provider's own terms.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">7. Indemnification</h2>
            <p>
              You agree to defend and hold ModishLog harmless from claims and reasonable costs
              arising out of (i) your use of the Service, (ii) your violation of these Terms, or
              (iii) your violation of any applicable law. We'll make reasonable efforts to notify
              you promptly of any such claim we become aware of.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">8. Disclaimers</h2>
            <p class="uppercase text-xs tracking-wide">
              The service is provided "as is" and "as available." to the fullest extent permitted
              by law, we disclaim all warranties, express or implied, including merchantability,
              fitness for a particular purpose, and non-infringement. We do not warrant that the
              service will be uninterrupted, error-free, or that ai-assisted suggestions,
              exchange-rate data, or any calculation the service produces will be accurate or
              suitable for your specific business decisions.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">9. Limitation of liability</h2>
            <p class="uppercase text-xs tracking-wide">
              To the maximum extent permitted by law: (a) ModishLog will not be liable for lost
              profits, lost data, or any indirect, consequential, incidental, or punitive damages
              arising from your use of (or inability to use) the service; and (b) our total
              liability to you for any claim arising under these terms is capped at the greater of
              (i) ₦50,000 and (ii) the amount you paid us for the service in the six months before
              the event giving rise to the claim.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">10. Term and termination</h2>
            <p>
              These Terms remain in effect while you use the Service. You may stop using the
              Service, or request closure of your account, at any time by contacting
              <a href="mailto:contact&#64;modishlog.com" class="text-emerald-600 hover:underline">contact&#64;modishlog.com</a>.
              We may suspend or terminate access if we believe you've materially violated these
              Terms, generally after giving you notice and a reasonable opportunity to fix the
              issue except where the violation poses an immediate security or legal risk. Sections
              2, 5&ndash;9, and 11&ndash;12 survive termination.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">11. Governing law and disputes</h2>
            <p>
              These Terms are governed by the laws of the Federal Republic of Nigeria. Before
              starting any formal proceeding, both parties agree to first try to resolve a dispute
              informally by contacting the other in writing and discussing in good faith. If that
              doesn't resolve things within 30 days, the courts of Lagos State, Nigeria have
              exclusive jurisdiction over any dispute arising out of or relating to these Terms or
              the Service, and both parties consent to that jurisdiction and venue.
            </p>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">12. General</h2>
            <ul class="list-disc pl-5 space-y-1">
              <li><strong>Changes to these Terms.</strong> We may update these Terms from time to time. We'll notify registered users by email at least 30 days before any material change, matching our Privacy Policy's notice practice. Continued use after the effective date of a change means you accept the updated Terms.</li>
              <li><strong>Electronic communications.</strong> By using the Service, you consent to receiving communications from us electronically (by email or in-app notice). These satisfy any legal requirement for written notice.</li>
              <li><strong>Accessibility.</strong> We aim to make the Service usable by everyone, including people with disabilities, and generally follow the Web Content Accessibility Guidelines (WCAG) 2.1 Level AA. If you hit an accessibility barrier, tell us at <a href="mailto:contact&#64;modishlog.com" class="text-emerald-600 hover:underline">contact&#64;modishlog.com</a> and we'll do our best to address it.</li>
              <li><strong>Entire agreement.</strong> These Terms, together with our Privacy Policy, are the entire agreement between you and ModishLog about your use of the Service. If any part of these Terms is found unenforceable, the rest remains in effect. Our failure to enforce a provision isn't a waiver of it. You may not assign these Terms without our consent; we may assign them as part of a merger, acquisition, or sale of assets.</li>
              <li><strong>Copyright.</strong> Copyright &copy; 2026 ModishLog. All rights reserved. Trademarks and logos displayed in the Service belong to ModishLog or their respective owners.</li>
            </ul>
          </section>

          <section>
            <h2 class="text-lg font-semibold text-gray-900 mb-2">13. Contact</h2>
            <p>
              Questions about these Terms? Email
              <a href="mailto:contact&#64;modishlog.com" class="text-emerald-600 hover:underline">contact&#64;modishlog.com</a>.
            </p>
          </section>

        </div>
      </div>
    </div>
  `,
})
export class TermsOfServicePageComponent {}
