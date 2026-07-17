<?php
/*
Plugin Name: ConversaPay AI Chatbot
Plugin URI: https://conversapay.com
Description: Effortless AI sales assistant for your website. Provides 24/7 customer service and automated checkout.
Version: 1.0.0
Author: ConversaPay
Author URI: https://conversapay.com
License: GPL2
*/

// Prevent direct access
if (!defined('ABSPATH')) {
    exit;
}

// Plugin settings option name
define('CONVERSAPAY_OPTION_NAME', 'conversapay_settings');

// ============================================
// Admin Menu
// ============================================

add_action('admin_menu', 'conversapay_add_admin_menu');

function conversapay_add_admin_menu() {
    add_options_page(
        'ConversaPay Settings',
        'ConversaPay',
        'manage_options',
        'conversapay',
        'conversapay_settings_page'
    );
}

// ============================================
// Settings Page
// ============================================

function conversapay_settings_page() {
    // Handle form submission
    if (isset($_POST['conversapay_save_settings']) && check_admin_referer('conversapay_save_settings')) {
        $business_id = sanitize_text_field($_POST['business_id']);
        $frontend_url = sanitize_text_field($_POST['frontend_url']);
        
        // Validate business ID format (alphanumeric, hyphens, underscores)
        if (!empty($business_id) && preg_match('/^[a-zA-Z0-9_-]+$/', $business_id)) {
            $settings = array(
                'business_id' => $business_id,
                'frontend_url' => !empty($frontend_url) ? $frontend_url : 'https://conversapay.com'
            );
            update_option(CONVERSAPAY_OPTION_NAME, $settings);
            echo '<div class="notice notice-success is-dismissible"><p>Settings saved successfully!</p></div>';
        } else {
            echo '<div class="notice notice-error"><p>Invalid Business ID format. Use only letters, numbers, hyphens, and underscores.</p></div>';
        }
    }
    
    // Get current settings
    $settings = get_option(CONVERSAPAY_OPTION_NAME, array());
    $business_id = isset($settings['business_id']) ? esc_attr($settings['business_id']) : '';
    $frontend_url = isset($settings['frontend_url']) ? esc_attr($settings['frontend_url']) : 'https://conversapay.com';
    ?>
    <div class="wrap">
        <h1>ConversaPay AI Chatbot Settings</h1>
        
        <div class="card" style="max-width: 600px; margin-top: 20px;">
            <h2>Configuration</h2>
            <p style="color: #666; margin-bottom: 20px;">
                Enter your Business ID from your ConversaPay dashboard to activate the chatbot on your website.
            </p>
            
            <form method="post" action="">
                <?php wp_nonce_field('conversapay_save_settings'); ?>
                
                <table class="form-table">
                    <tr>
                        <th scope="row">
                            <label for="business_id">Business ID</label>
                        </th>
                        <td>
                            <input type="text" 
                                   id="business_id" 
                                   name="business_id" 
                                   value="<?php echo $business_id; ?>" 
                                   class="regular-text"
                                   placeholder="e.g., my-business-123"
                                   required>
                            <p class="description">
                                Find this ID in your <a href="https://conversapay.com/dashboard" target="_blank">ConversaPay Dashboard</a>
                            </p>
                        </td>
                    </tr>
                    
                    <tr>
                        <th scope="row">
                            <label for="frontend_url">Frontend URL</label>
                        </th>
                        <td>
                            <input type="url" 
                                   id="frontend_url" 
                                   name="frontend_url" 
                                   value="<?php echo $frontend_url; ?>" 
                                   class="regular-text">
                            <p class="description">
                                Your ConversaPay frontend URL (usually https://conversapay.com)
                            </p>
                        </td>
                    </tr>
                </table>
                
                <?php submit_button('Save Settings', 'primary', 'conversapay_save_settings'); ?>
            </form>
        </div>
        
        <?php if (!empty($business_id)): ?>
        <div class="card" style="max-width: 600px; margin-top: 20px;">
            <h2>Status</h2>
            <p style="color: #10b981; font-size: 1.1em;">
                ✓ Chatbot is <strong>active</strong> on your website!
            </p>
            <p>
                <strong>Business ID:</strong> <code><?php echo $business_id; ?></code>
            </p>
            <p style="color: #666; font-size: 0.9em;">
                The chatbot widget will appear in the bottom-left corner of your website.
            </p>
        </div>
        <?php else: ?>
        <div class="card" style="max-width: 600px; margin-top: 20px;">
            <h2>Status</h2>
            <p style="color: #f59e0b;">
                ⚠ Chatbot is <strong>inactive</strong>. Please configure your Business ID above.
            </p>
        </div>
        <?php endif; ?>
        
        <div class="card" style="max-width: 600px; margin-top: 20px;">
            <h2>Need Help?</h2>
            <p>
                Visit <a href="https://conversapay.com" target="_blank">conversapay.com</a> to:
            </p>
            <ul>
                <li>Create your Business ID</li>
                <li>Configure your products and pricing</li>
                <li>Customize the chatbot behavior</li>
                <li>View orders and analytics</li>
            </ul>
        </div>
    </div>
    <?php
}

// ============================================
// Widget Injection
// ============================================

add_action('wp_footer', 'conversapay_inject_widget');

function conversapay_inject_widget() {
    $settings = get_option(CONVERSAPAY_OPTION_NAME, array());
    
    if (empty($settings['business_id'])) {
        return; // Don't inject if not configured
    }
    
    $business_id = esc_js($settings['business_id']);
    $frontend_url = esc_url($settings['frontend_url']);
    ?>
    <!-- ConversaPay AI Chatbot Widget -->
    <script>
        window.ConversaPayWidgetConfig = {
            business_id: "<?php echo $business_id; ?>"
        };
    </script>
    <script src="<?php echo $frontend_url; ?>/frontend/js/widget.js" defer></script>
    <?php
}

// ============================================
// Activation/Deactivation Hooks
// ============================================

register_activation_hook(__FILE__, 'conversapay_activate');
function conversapay_activate() {
    // Set default settings on activation
    $default_settings = array(
        'business_id' => '',
        'frontend_url' => 'https://conversapay.com'
    );
    add_option(CONVERSAPAY_OPTION_NAME, $default_settings);
}

register_deactivation_hook(__FILE__, 'conversapay_deactivate');
function conversapay_deactivate() {
    // Keep settings on deactivation (user might want to re-enable later)
    // To completely remove settings, uncomment the line below:
    // delete_option(CONVERSAPAY_OPTION_NAME);
}

// ============================================
// Uninstall Hook (cleanup)
// ============================================

register_uninstall_hook(__FILE__, 'conversapay_uninstall');
function conversapay_uninstall() {
    // Delete all plugin data on uninstall
    delete_option(CONVERSAPAY_OPTION_NAME);
}

?>