<?php
/**
 * Plugin Name: ConversaPay AI Chat Assistant
 * Plugin URI: https://conversapay.org
 * Description: AI-powered chat widget that sells products and processes payments automatically. Embed a smart sales agent on your WordPress site in seconds.
 * Version: 1.0.0
 * Author: ConversaPay Team
 * Author URI: https://conversapay.org
 * License: Proprietary
 * Text Domain: conversapay-chat
 * Domain Path: /languages
 */

// Prevent direct access
if (!defined('ABSPATH')) {
    exit;
}

// ============================================
// Plugin Constants
// ============================================

define('CONVERSAPAY_CHAT_VERSION', '1.0.0');
define('CONVERSAPAY_CHAT_PLUGIN_DIR', plugin_dir_path(__FILE__));
define('CONVERSAPAY_CHAT_PLUGIN_URL', plugin_dir_url(__FILE__));
define('CONVERSAPAY_CHAT_OPTION_KEY', 'conversapay_chat_settings');

// ============================================
// Admin Menu
// ============================================

function conversapay_chat_admin_menu() {
    add_options_page(
        'ConversaPay AI Chat Settings',
        'ConversaPay Chat',
        'manage_options',
        'conversapay-chat',
        'conversapay_chat_settings_page'
    );
}
add_action('admin_menu', 'conversapay_chat_admin_menu');

// ============================================
// Settings Registration
// ============================================

function conversapay_chat_register_settings() {
    register_setting(
        'conversapay_chat_settings_group',
        CONVERSAPAY_CHAT_OPTION_KEY,
        array(
            'type' => 'array',
            'sanitize_callback' => 'conversapay_chat_sanitize_settings',
            'default' => array(
                'business_id' => '',
                'frontend_url' => '',
                'widget_position' => 'bottom-right',
                'widget_color' => '#A855F7',
                'enable_on_pages' => 'all'
            )
        )
    );
}
add_action('admin_init', 'conversapay_chat_register_settings');

function conversapay_chat_sanitize_settings($input) {
    $sanitized = array();
    
    // Sanitize business ID
    if (isset($input['business_id'])) {
        $sanitized['business_id'] = sanitize_text_field($input['business_id']);
    }
    
    // Sanitize frontend URL
    if (isset($input['frontend_url'])) {
        $sanitized['frontend_url'] = esc_url_raw($input['frontend_url']);
    }
    
    // Sanitize widget position
    if (isset($input['widget_position'])) {
        $allowed_positions = array('bottom-right', 'bottom-left');
        $sanitized['widget_position'] = in_array($input['widget_position'], $allowed_positions) 
            ? $input['widget_position'] 
            : 'bottom-right';
    }
    
    // Sanitize widget color
    if (isset($input['widget_color'])) {
        $sanitized['widget_color'] = sanitize_hex_color($input['widget_color']);
    }
    
    // Sanitize enable on pages
    if (isset($input['enable_on_pages'])) {
        $sanitized['enable_on_pages'] = sanitize_text_field($input['enable_on_pages']);
    }
    
    return $sanitized;
}

// ============================================
// Admin Settings Page
// ============================================

function conversapay_chat_settings_page() {
    // Get current settings
    // The business_id and frontend_url may be pre-filled by the backend
    // substitution engine when the plugin is downloaded from the dashboard.
    $settings = get_option(CONVERSAPAY_CHAT_OPTION_KEY, array());
    $business_id = isset($settings['business_id']) ? esc_attr($settings['business_id']) : '';
    $frontend_url = isset($settings['frontend_url']) ? esc_attr($settings['frontend_url']) : '';
    $widget_position = isset($settings['widget_position']) ? esc_attr($settings['widget_position']) : 'bottom-right';
    $widget_color = isset($settings['widget_color']) ? esc_attr($settings['widget_color']) : '#A855F7';
    $enable_on_pages = isset($settings['enable_on_pages']) ? esc_attr($settings['enable_on_pages']) : 'all';
    ?>
    
    <div class="wrap">
        <h1>ConversaPay AI Chat Assistant</h1>
        
        <div class="card" style="max-width: 800px; margin-top: 20px;">
            <h2 style="margin-top: 0;">Widget Configuration</h2>
            <p style="color: #666; margin-bottom: 20px;">
                Configure your AI chat widget. Get your Business ID from your 
                <a href="https://conversapay.org/dashboard" target="_blank">ConversaPay Dashboard</a>.
            </p>
            
            <form method="post" action="options.php">
                <?php
                settings_fields('conversapay_chat_settings_group');
                do_settings_sections('conversapay_chat_settings_group');
                ?>
                
                <table class="form-table">
                    <tr>
                        <th scope="row">
                            <label for="business_id">Business ID</label>
                        </th>
                        <td>
                            <input 
                                type="text" 
                                id="business_id" 
                                name="<?php echo CONVERSAPAY_CHAT_OPTION_KEY; ?>[business_id]" 
                                value="<?php echo $business_id; ?>" 
                                class="regular-text"
                                placeholder="e.g., my_business_name"
                                required
                            >
                            <p class="description">
                                Enter your ConversaPay Business ID. You can find this in your dashboard.
                                <?php if (!empty($business_id) && $business_id !== '{{BUSINESS_ID}}'): ?>
                                    <strong style="color: #10b981;">✓ Pre-filled from your dashboard.</strong>
                                <?php endif; ?>
                            </p>
                        </td>
                    </tr>
                    
                    <tr>
                        <th scope="row">
                            <label for="frontend_url">Frontend URL</label>
                        </th>
                        <td>
                            <input 
                                type="text" 
                                id="frontend_url" 
                                name="<?php echo CONVERSAPAY_CHAT_OPTION_KEY; ?>[frontend_url]" 
                                value="<?php echo $frontend_url; ?>" 
                                class="regular-text"
                                placeholder="https://conversapay.org"
                            >
                            <p class="description">
                                The ConversaPay frontend URL for loading the chat widget.
                                <?php if (!empty($frontend_url) && $frontend_url !== '{{FRONTEND_URL}}'): ?>
                                    <strong style="color: #10b981;">✓ Pre-filled from your dashboard.</strong>
                                <?php endif; ?>
                            </p>
                        </td>
                    </tr>
                    
                    <tr>
                        <th scope="row">
                            <label for="widget_position">Widget Position</label>
                        </th>
                        <td>
                            <select id="widget_position" name="<?php echo CONVERSAPAY_CHAT_OPTION_KEY; ?>[widget_position]">
                                <option value="bottom-right" <?php selected($widget_position, 'bottom-right'); ?>>Bottom Right</option>
                                <option value="bottom-left" <?php selected($widget_position, 'bottom-left'); ?>>Bottom Left</option>
                            </select>
                            <p class="description">
                                Choose where the chat widget appears on your site.
                            </p>
                        </td>
                    </tr>
                    
                    <tr>
                        <th scope="row">
                            <label for="widget_color">Widget Color</label>
                        </th>
                        <td>
                            <input 
                                type="color" 
                                id="widget_color" 
                                name="<?php echo CONVERSAPAY_CHAT_OPTION_KEY; ?>[widget_color]" 
                                value="<?php echo $widget_color; ?>"
                            >
                            <p class="description">
                                Customize the primary color of your chat widget.
                            </p>
                        </td>
                    </tr>
                    
                    <tr>
                        <th scope="row">
                            <label for="enable_on_pages">Enable On</label>
                        </th>
                        <td>
                            <select id="enable_on_pages" name="<?php echo CONVERSAPAY_CHAT_OPTION_KEY; ?>[enable_on_pages]">
                                <option value="all" <?php selected($enable_on_pages, 'all'); ?>>All Pages</option>
                                <option value="homepage" <?php selected($enable_on_pages, 'homepage'); ?>>Homepage Only</option>
                                <option value="selected" <?php selected($enable_on_pages, 'selected'); ?>>Selected Pages</option>
                            </select>
                            <p class="description">
                                Choose where to display the chat widget.
                            </p>
                        </td>
                    </tr>
                </table>
                
                <?php submit_button('Save Settings'); ?>
            </form>
        </div>
        
        <div class="card" style="max-width: 800px; margin-top: 20px;">
            <h2>Preview</h2>
            <p style="color: #666; margin-bottom: 20px;">
                Your chat widget will appear like this on your website:
            </p>
            
            <div style="background: #f0f0f0; padding: 40px; border-radius: 8px; text-align: center;">
                <div style="background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h3>Your Website Content</h3>
                    <p style="color: #666;">The chat widget will appear in the corner of every page.</p>
                    
                    <div style="margin-top: 40px; padding: 20px; background: #f9f9f9; border-radius: 8px; text-align: left;">
                        <strong>Widget Preview:</strong><br>
                        <div style="width: 60px; height: 60px; background: linear-gradient(135deg, #A855F7, #3B82F6); border-radius: 50%; margin: 20px auto; box-shadow: 0 4px 20px rgba(168, 85, 247, 0.4);"></div>
                        <p style="color: #666; font-size: 0.9rem;">Click to open chat</p>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="card" style="max-width: 800px; margin-top: 20px;">
            <h2>Installation Complete!</h2>
            <p style="color: #666; margin-bottom: 20px;">
                Your ConversaPay AI Chat widget is now active on your site. 
                Customers can start chatting and purchasing immediately.
            </p>
            
            <h3>What's Next?</h3>
            <ul style="line-height: 2;">
                <li>✅ Configure your products in the <a href="https://conversapay.org/dashboard" target="_blank">ConversaPay Dashboard</a></li>
                <li>✅ Customize your AI agent's personality and responses</li>
                <li>✅ Test the widget by clicking the chat icon on your site</li>
                <li>✅ Monitor conversations and sales in real-time</li>
            </ul>
            
            <h3 style="margin-top: 30px;">Need Help?</h3>
            <p style="color: #666;">
                Visit our <a href="https://conversapay.org/docs" target="_blank">documentation</a> or 
                contact <a href="mailto:support@conversapay.org">support@conversapay.org</a>
            </p>
        </div>
    </div>
    
    <?php
}

// ============================================
// Frontend Widget Injection
// ============================================

function conversapay_chat_inject_widget() {
    // Get settings
    $settings = get_option(CONVERSAPAY_CHAT_OPTION_KEY, array());
    $business_id = isset($settings['business_id']) ? $settings['business_id'] : '';
    $frontend_url = isset($settings['frontend_url']) ? $settings['frontend_url'] : '';
    
    // Don't inject if no business ID configured
    if (empty($business_id)) {
        return;
    }
    
    // Check if we should enable on this page
    $enable_on_pages = isset($settings['enable_on_pages']) ? $settings['enable_on_pages'] : 'all';
    
    if ($enable_on_pages === 'homepage' && !is_front_page()) {
        return;
    }
    
    if ($enable_on_pages === 'selected') {
        $enabled_pages = get_option('conversapay_chat_enabled_pages', array());
        if (!in_array(get_the_ID(), $enabled_pages)) {
            return;
        }
    }
    
    // Get widget customization
    $widget_position = isset($settings['widget_position']) ? $settings['widget_position'] : 'bottom-right';
    $widget_color = isset($settings['widget_color']) ? $settings['widget_color'] : '#A855F7';
    
    // Build the widget URL - use frontend_url if provided, otherwise fall back to plugin URL
    if (!empty($frontend_url) && $frontend_url !== '{{FRONTEND_URL}}') {
        $widget_url = rtrim($frontend_url, '/') . '/frontend/js/widget.js';
    } else {
        $widget_url = CONVERSAPAY_CHAT_PLUGIN_URL . '../frontend/js/widget.js';
    }
    
    // Inject the widget script
    ?>
    <script 
        src="<?php echo esc_url($widget_url); ?>" 
        data-business-id="<?php echo esc_attr($business_id); ?>"
        data-position="<?php echo esc_attr($widget_position); ?>"
        data-color="<?php echo esc_attr($widget_color); ?>"
        defer
    ></script>
    <?php
}
add_action('wp_footer', 'conversapay_chat_inject_widget');

// ============================================
// Plugin Activation/Deactivation
// ============================================

function conversapay_chat_activate() {
    // Initialize default settings with template hooks
    // The {{BUSINESS_ID}} and {{FRONTEND_URL}} tokens are replaced
    // by the ConversaPay backend substitution engine when the plugin
    // is downloaded from the dashboard.
    $default_settings = array(
        'business_id'  => '{{BUSINESS_ID}}',
        'frontend_url' => '{{FRONTEND_URL}}',
        'widget_position' => 'bottom-right',
        'widget_color' => '#A855F7',
        'enable_on_pages' => 'all'
    );
    
    if (!get_option(CONVERSAPAY_CHAT_OPTION_KEY)) {
        add_option(CONVERSAPAY_CHAT_OPTION_KEY, $default_settings);
    }
}
register_activation_hook(__FILE__, 'conversapay_chat_activate');

function conversapay_chat_deactivate() {
    // Cleanup if needed
}
register_deactivation_hook(__FILE__, 'conversapay_chat_deactivate');

// ============================================
// AJAX Handler for saving enabled pages
// ============================================

function conversapay_chat_save_enabled_pages() {
    if (!wp_verify_nonce($_POST['nonce'], 'conversapay_chat_nonce')) {
        wp_die('Security check failed');
    }
    
    if (!current_user_can('manage_options')) {
        wp_die('Unauthorized');
    }
    
    $pages = isset($_POST['pages']) ? array_map('intval', $_POST['pages']) : array();
    update_option('conversapay_chat_enabled_pages', $pages);
    
    wp_send_json_success(array('message' => 'Settings saved successfully'));
}
add_action('wp_ajax_conversapay_chat_save_pages', 'conversapay_chat_save_enabled_pages');

// ============================================
// Enqueue Admin Assets
// ============================================

function conversapay_chat_admin_assets($hook) {
    // Only load on our settings page
    if ($hook !== 'settings_page_conversapay-chat') {
        return;
    }
    
    wp_enqueue_style(
        'conversapay-chat-admin',
        CONVERSAPAY_CHAT_PLUGIN_URL . 'admin.css',
        array(),
        CONVERSAPAY_CHAT_VERSION
    );
}
add_action('admin_enqueue_scripts', 'conversapay_chat_admin_assets');

// ============================================
// Helper Functions
// ============================================

/**
 * Get widget settings
 * 
 * @return array Widget settings
 */
function conversapay_chat_get_settings() {
    return get_option(CONVERSAPAY_CHAT_OPTION_KEY, array());
}

/**
 * Check if widget is enabled
 * 
 * @return bool True if widget is enabled
 */
function conversapay_chat_is_enabled() {
    $settings = conversapay_chat_get_settings();
    return !empty($settings['business_id']);
}

// ============================================
// Logging
// ============================================

function conversapay_chat_log($message, $level = 'info') {
    if (WP_DEBUG && WP_DEBUG_LOG) {
        error_log("[ConversaPay Chat] {$message}");
    }
}

// Log plugin load
conversapay_chat_log('Plugin loaded successfully');