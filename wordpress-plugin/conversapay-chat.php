<?php
/**
 * Plugin Name: ConversaPay AI Chat Assistant
 * Description: Responsive ConversaPay sales chat with a guided WordPress setup screen and shortcode embed.
 * Version: 1.1.0
 * Author: ConversaPay Team
 * License: Proprietary
 * Text Domain: conversapay-chat
 */
if (!defined('ABSPATH')) { exit; }

define('CONVERSAPAY_CHAT_VERSION', '1.1.0');
define('CONVERSAPAY_CHAT_PLUGIN_DIR', plugin_dir_path(__FILE__));
define('CONVERSAPAY_CHAT_PLUGIN_URL', plugin_dir_url(__FILE__));
define('CONVERSAPAY_CHAT_OPTION_KEY', 'conversapay_chat_settings');

function conversapay_chat_defaults() { return array('business_id'=>'','frontend_url'=>'https://www.conversapay.org','api_key'=>'','widget_position'=>'bottom-right','widget_color'=>'#635bff','enable_on_pages'=>'all','enabled_pages'=>array()); }
function conversapay_chat_settings() { return wp_parse_args((array)get_option(CONVERSAPAY_CHAT_OPTION_KEY, array()), conversapay_chat_defaults()); }
function conversapay_chat_admin_menu() { add_options_page('ConversaPay Chat','ConversaPay Chat','manage_options','conversapay-chat','conversapay_chat_settings_page'); }
add_action('admin_menu','conversapay_chat_admin_menu');
function conversapay_chat_register_settings() { register_setting('conversapay_chat_settings_group', CONVERSAPAY_CHAT_OPTION_KEY, array('type'=>'array','sanitize_callback'=>'conversapay_chat_sanitize_settings','default'=>conversapay_chat_defaults())); }
add_action('admin_init','conversapay_chat_register_settings');
function conversapay_chat_sanitize_settings($input) {
  $defaults=conversapay_chat_defaults(); $input=is_array($input)?$input:array(); $out=$defaults;
  $out['business_id']=sanitize_text_field($input['business_id']??''); $out['frontend_url']=esc_url_raw($input['frontend_url']??$defaults['frontend_url']); $out['api_key']=sanitize_text_field($input['api_key']??'');
  $out['widget_position']=in_array(($input['widget_position']??''),array('bottom-right','bottom-left'),true)?$input['widget_position']:$defaults['widget_position']; $out['widget_color']=sanitize_hex_color($input['widget_color']??'')?:$defaults['widget_color'];
  $out['enable_on_pages']=in_array(($input['enable_on_pages']??''),array('all','homepage','selected'),true)?$input['enable_on_pages']:'all'; $out['enabled_pages']=array_values(array_filter(array_map('absint',(array)($input['enabled_pages']??array())))); return $out;
}
function conversapay_chat_settings_page() {
  if (!current_user_can('manage_options')) return; $s=conversapay_chat_settings(); $pages=get_pages(array('sort_column'=>'post_title','post_status'=>'publish')); ?>
  <div class="wrap cp-admin"><div class="cp-admin-hero"><div><span class="cp-admin-kicker">CONVERSAPAY</span><h1>Chat operations</h1><p>הטמעה, תצוגה ובדיקת חיבור ממסך אחד. אין צורך לערוך קוד באתר.</p></div><a class="button button-primary" href="https://www.conversapay.org/dashboard" target="_blank" rel="noopener">פתח Dashboard</a></div>
  <div class="cp-admin-grid"><section class="cp-admin-card"><h2>חיבור הווידג'ט</h2><p class="description">הדבק את הנתונים מהדאשבורד. הווידג'ט ייטען בצורה מותאמת למובייל ולמחשב.</p><form method="post" action="options.php"><?php settings_fields('conversapay_chat_settings_group'); ?>
  <table class="form-table" role="presentation"><tr><th><label for="cp_business_id">Business ID</label></th><td><input class="regular-text" id="cp_business_id" name="<?php echo esc_attr(CONVERSAPAY_CHAT_OPTION_KEY); ?>[business_id]" value="<?php echo esc_attr($s['business_id']); ?>" required><p class="description">UUID של העסק מתוך ConversaPay.</p></td></tr>
  <tr><th><label for="cp_frontend_url">ConversaPay URL</label></th><td><input class="regular-text" type="url" id="cp_frontend_url" name="<?php echo esc_attr(CONVERSAPAY_CHAT_OPTION_KEY); ?>[frontend_url]" value="<?php echo esc_attr($s['frontend_url']); ?>" required></td></tr>
  <tr><th><label for="cp_api_key">Widget API Key</label></th><td><input class="regular-text" id="cp_api_key" name="<?php echo esc_attr(CONVERSAPAY_CHAT_OPTION_KEY); ?>[api_key]" value="<?php echo esc_attr($s['api_key']); ?>"><p class="description">אופציונלי, מומלץ במסלולי PRO ו-PREMIUM.</p></td></tr>
  <tr><th>מיקום</th><td><select name="<?php echo esc_attr(CONVERSAPAY_CHAT_OPTION_KEY); ?>[widget_position]"><option value="bottom-right" <?php selected($s['widget_position'],'bottom-right'); ?>>ימין למטה</option><option value="bottom-left" <?php selected($s['widget_position'],'bottom-left'); ?>>שמאל למטה</option></select></td></tr>
  <tr><th>צבע</th><td><input type="color" name="<?php echo esc_attr(CONVERSAPAY_CHAT_OPTION_KEY); ?>[widget_color]" value="<?php echo esc_attr($s['widget_color']); ?>"></td></tr>
  <tr><th>הצגה באתר</th><td><select id="cp_enable_on_pages" name="<?php echo esc_attr(CONVERSAPAY_CHAT_OPTION_KEY); ?>[enable_on_pages]"><option value="all" <?php selected($s['enable_on_pages'],'all'); ?>>כל העמודים</option><option value="homepage" <?php selected($s['enable_on_pages'],'homepage'); ?>>דף הבית בלבד</option><option value="selected" <?php selected($s['enable_on_pages'],'selected'); ?>>עמודים נבחרים</option></select><div id="cp_selected_pages" class="cp-page-picker" <?php echo $s['enable_on_pages']==='selected'?'':'hidden'; ?>><?php foreach($pages as $page): ?><label><input type="checkbox" name="<?php echo esc_attr(CONVERSAPAY_CHAT_OPTION_KEY); ?>[enabled_pages][]" value="<?php echo esc_attr($page->ID); ?>" <?php checked(in_array($page->ID,$s['enabled_pages'],true)); ?>> <?php echo esc_html($page->post_title); ?></label><?php endforeach; ?></div></td></tr></table><?php submit_button('שמור והפעל'); ?></form></section>
  <aside class="cp-admin-card cp-admin-preview"><span class="cp-admin-kicker">LIVE CHECK</span><h2>מצב ההטמעה</h2><div class="cp-status <?php echo $s['business_id']?'is-ready':'is-waiting'; ?>"><span></span><?php echo $s['business_id']?'מוכן לטעינה באתר':'ממתין ל-Business ID'; ?></div><p>אפשר להטמיע גם בתוך תוכן בעזרת:</p><code>[conversapay_chat]</code><p class="description">שימוש ב-shortcode עוקף את כללי הצגת העמודים ומאפשר שליטה נקודתית.</p><a class="button" href="<?php echo esc_url(admin_url('options-general.php?page=conversapay-chat')); ?>">רענן מצב</a></aside></div></div>
  <script>document.getElementById('cp_enable_on_pages')?.addEventListener('change',function(){document.getElementById('cp_selected_pages').hidden=this.value!=='selected';});</script><?php
}
function conversapay_chat_should_render() { $s=conversapay_chat_settings(); if (!$s['business_id']) return false; if ($s['enable_on_pages']==='homepage') return is_front_page(); if ($s['enable_on_pages']==='selected') return in_array(get_queried_object_id(),$s['enabled_pages'],true); return true; }
function conversapay_chat_markup() { $s=conversapay_chat_settings(); if (!$s['business_id']) return ''; $url=rtrim($s['frontend_url'],'/').'/frontend/js/widget.js'; return sprintf('<script src="%s" data-business-id="%s" data-api-key="%s" data-position="%s" data-color="%s" defer></script>',esc_url($url),esc_attr($s['business_id']),esc_attr($s['api_key']),esc_attr($s['widget_position']),esc_attr($s['widget_color'])); }
function conversapay_chat_inject_widget() { if (conversapay_chat_should_render()) echo conversapay_chat_markup(); }
add_action('wp_footer','conversapay_chat_inject_widget');
function conversapay_chat_shortcode() { return conversapay_chat_markup(); }
add_shortcode('conversapay_chat','conversapay_chat_shortcode');
function conversapay_chat_admin_assets($hook) { if ($hook==='settings_page_conversapay-chat') wp_enqueue_style('conversapay-chat-admin',CONVERSAPAY_CHAT_PLUGIN_URL.'admin.css',array(),CONVERSAPAY_CHAT_VERSION); }
add_action('admin_enqueue_scripts','conversapay_chat_admin_assets');
function conversapay_chat_activate() { if (!get_option(CONVERSAPAY_CHAT_OPTION_KEY)) add_option(CONVERSAPAY_CHAT_OPTION_KEY,conversapay_chat_defaults()); }
register_activation_hook(__FILE__,'conversapay_chat_activate');
function conversapay_chat_get_settings() { return conversapay_chat_settings(); }
function conversapay_chat_is_enabled() { return (bool)conversapay_chat_settings()['business_id']; }
