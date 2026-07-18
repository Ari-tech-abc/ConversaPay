# ConversaPay AI Chat Assistant - WordPress Plugin

Transform your WordPress website into an AI-powered sales machine with ConversaPay's intelligent chat widget.

## 🚀 Features

- **AI-Powered Sales**: Automatically sells products and processes payments through chat
- **One-Click Installation**: Simple setup with just your Business ID
- **Fully Customizable**: Match your brand with custom colors and positioning
- **Mobile Responsive**: Perfect experience on all devices
- **Real-Time Analytics**: Monitor conversations and sales in your dashboard
- **Secure & Fast**: Domain-validated widget loading with optimized performance

## 📋 Requirements

- WordPress 5.0 or higher
- PHP 7.4 or higher
- A ConversaPay account (sign up at [conversapay.org](https://conversapay.org))
- A Business ID from your ConversaPay dashboard

## 🔧 Installation

### Method 1: Upload via WordPress Admin

1. Download the plugin files
2. Go to **WordPress Admin → Plugins → Add New → Upload Plugin**
3. Choose the `conversapay-chat.php` file
4. Click **Install Now**
5. Activate the plugin

### Method 2: Manual Installation

1. Upload the `conversapay-chat.php` file to `/wp-content/plugins/` directory
2. Go to **WordPress Admin → Plugins**
3. Find "ConversaPay AI Chat Assistant" and click **Activate**

## ⚙️ Configuration

1. After activation, go to **Settings → ConversaPay Chat**
2. Enter your **Business ID** (found in your ConversaPay Dashboard)
3. Customize widget settings:
   - **Position**: Bottom-right or bottom-left
   - **Color**: Primary widget color
   - **Pages**: All pages, homepage only, or selected pages
4. Click **Save Settings**

## 🎯 How to Get Your Business ID

1. Sign up at [conversapay.org](https://conversapay.org)
2. Create your business in the dashboard
3. Go to **Settings → Integrations**
4. Copy your Business ID (e.g., `my_business_name`)

## 💬 How It Works

1. **Visitor arrives** on your WordPress site
2. **Chat widget appears** in the corner (customizable position)
3. **Visitor clicks** the chat icon
4. **AI assistant greets** them and starts conversation
5. **Products are suggested** based on conversation
6. **Payments processed** directly in the chat via Stripe
7. **You get notified** of every sale in real-time

## 🎨 Customization

### Widget Position
Choose between bottom-right or bottom-left corner placement.

### Brand Colors
Customize the primary color to match your brand identity.

### Page Targeting
- **All Pages**: Widget appears on every page
- **Homepage Only**: Widget appears only on the front page
- **Selected Pages**: Choose specific pages for widget display

## 🔒 Security & Privacy

- **Domain Validation**: Widget only loads on authorized domains
- **No Data Storage**: Chat widget doesn't store personal data on your server
- **Secure API**: All communications encrypted via HTTPS
- **GDPR Compliant**: Built with privacy regulations in mind

## 📊 Analytics & Monitoring

Monitor your AI assistant's performance in the ConversaPay Dashboard:
- Total conversations
- Conversion rates
- Revenue generated
- Popular products
- Customer satisfaction

## 🛠️ Troubleshooting

### Widget Not Appearing

1. **Check Business ID**: Ensure you've entered the correct Business ID in settings
2. **Clear Cache**: Clear WordPress cache and browser cache
3. **Check Console**: Open browser console (F12) for any JavaScript errors
4. **Verify Domain**: Ensure your domain is added to allowed domains in ConversaPay dashboard

### Chat Not Responding

1. **Check API Status**: Visit `/api/v1/health` to verify backend is running
2. **Verify Products**: Ensure products are configured in your dashboard
3. **Check Logs**: Enable WordPress debug mode to see detailed errors

### Styling Issues

1. **Theme Conflicts**: Some WordPress themes may conflict with widget styles
2. **CSS Priority**: Widget uses high z-index (99999) to stay on top
3. **Responsive Issues**: Widget automatically adjusts for mobile devices

## 🔄 Updates

### Automatic Updates
- Enable automatic updates in WordPress plugin settings
- Updates are delivered via WordPress update system

### Manual Updates
1. Download the latest version
2. Deactivate and delete the current plugin
3. Upload and activate the new version
4. Re-enter your Business ID in settings

## 📞 Support

- **Documentation**: [conversapay.org/docs](https://conversapay.org/docs)
- **Email Support**: support@conversapay.org
- **Dashboard Help**: Available in your ConversaPay dashboard

## 🔗 Integration with ConversaPay Ecosystem

This plugin is part of the complete ConversaPay platform:
- **Dashboard**: Manage products, view analytics, customize AI
- **Mobile App**: Monitor sales on the go
- **API Access**: Build custom integrations
- **Webhook Support**: Connect to your existing systems

## 📝 Changelog

### Version 1.0.0
- Initial release
- Basic chat widget functionality
- Admin settings page
- Domain-based security
- Customizable colors and positions

## 📄 License

Proprietary - ConversaPay Team

## 🙏 Credits

Built with ❤️ by the ConversaPay Team

---

**Ready to transform your WordPress site into a sales machine?** Get started at [conversapay.org](https://conversapay.org)