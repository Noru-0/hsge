# Untitled

tôi cần làm 1 docs để báo cáo cho thầy tôi biết là câu hỏi mà tôi tính nhờ thầy tham mưu đã được tôi tìm ra đáp án, báo cáo này có thể có những thứ chưa đúng với code hiện tại nhé, nói về các vấn đề sau:

- Vấn đề đã tính nhờ thầy tham mưu:
    - Về Pre-condition và Post-condition để nối các Operator với nhau:
        - việc hardcode sẵn 1 list các Pre-condition và Post-condition phổ biến và dùng rule để xác định là chưa tốt, nên đã chuyển sang nhờ LLM
        - việc so sánh Pre-condition và Post-condition do LLM tạo bằng logic thông thường là chưa tốt, bởi vì được tạo ra nhờ LLM sau khi đã được cho xem trạng thái trước và sau khi thực hiện Skill → không tạo được Operator Graph đúng dẫn tới không có Curriculum đúng → không tạo được SEMANTIC TASK
- Giải pháp đã dùng:
    - Về Pre-condition và Post-condition:
        - so sánh Embedding ( cái này đọc code để biết thêm)

Nhưng trước tiên phải nói sơ về agent để thầy nắm thông tin

- Mục tiêu của agent (có thể khám phá các task SEMANTIC trên 1 web domain bất kỳ, thực hiện task đó để làm dữ liệu training)
- Nói tổng quan về flow explore 1 cách cơ bản và dễ hiểu: task ở đâu ra; flow Explore ra sao; Skill, Operator, Curriculum được tạo ra sao, bọn chúng có ý nghĩa gì để tạo ra SEMANTIC TRAJECTORY
- Kết quả:
    - Khi chạy Explore lại thử thì có nhiều task thành công hơn đáng kể, tỷ lệ task pass tăng lên `101/122 = **82.8%**` , cụ thể:
        
        
        | Run | Time | Domain | Nodes | Tasks | API cost |
        | --- | --- | --- | --- | --- | --- |
        | wa_shopping_run_25  | 1h 17m 17s | Shopping | 58 | 122 | 2.9$ (openAI gpt-4o)
        0.4$ (Deepseek V4 flash) |
        
        | Task family | Run 25 |
        | --- | --- |
        | Search | 14/15 = **93.3%** |
        | Feedback/read information | 21/24 = **87.5%** |
        | Other navigation/information tasks | 31/34 = **91.2%** |
        | Analysis | 23/24 = **95.8%** |
        | State change | 10/22 = **45.5%** |
    - Đã tạo đúng Curriculum, kết quả là xuất hiện Semantic Task (có thể có các task Semantic hơn nữa nếu chạy thêm):
        
        ```json
        {
          "schema_version": "semantic-v1",
          "episode_id": "semantic_shopping_001",
          "synthetic": true,
          "domain": "shopping",
          "task_origin": "semantic",
          "task": "Find a 1 TB portable SSD, sort the results by lowest price, open the cheapest suitable item, confirm that it is in stock, select the 1 TB option, add one unit to the cart, and report the cart subtotal.",
          "difficulty": 7,
          "outcome": {
            "status": "success",
            "success": true,
            "reward": 1.0,
            "final_answer": "The selected 1 TB portable SSD is in the cart with quantity 1; the  cart subtotal is $79.99."
          },
          "safety": {
            "checkout_mode": "safe",
            "irreversible_action_allowed": false
          },
          "initial_state": {
            "url": "http://192.168.1.31:7770/",
            "predicates": [
              "has_search_input",
              "has_menu",
              "view:collection"
            ]
          },
          "skill_chain": [
            {
              "order": 1,
              "skill_id": "skill_submit_search_query",
              "skill_name": "submit_search_query",
              "semantic_goal": "Search the catalog for 1 TB portable SSD products.",
              "preconditions": ["has_search_input"],
              "actions": ["fill('search_box', '1 TB portable SSD')", "press('search_box', 'ENTER')"],
              "effects": ["results_shown", "has_filter_or_sort"],
              "state_before": ["has_search_input", "view:collection"],
              "state_after": ["has_search_input", "results_shown", "has_filter_or_sort", "view:collection"],
              "evidence": "Search result heading and Sort By control are visible."
            },
            {
              "order": 2,
              "skill_id": "skill_inspect_filter_sort",
              "skill_name": "inspect_filter_sort",
              "semantic_goal": "Sort matching products from lowest to highest price.",
              "preconditions": ["results_shown", "has_filter_or_sort"],
              "actions": ["click('sort_by')", "select_option('sort_by', 'Price')"],
              "effects": ["results_sorted_by_price"],
              "state_before": ["results_shown", "has_filter_or_sort"],
              "state_after": ["results_shown", "has_filter_or_sort", "results_sorted_by_price"],
              "evidence": "Sort By displays Price and the first result has the lowest visible price."
            },
            {
              "order": 3,
              "skill_id": "skill_open_visible_item",
              "skill_name": "open_visible_item",
              "semantic_goal": "Open the cheapest suitable 1 TB portable SSD.",
              "preconditions": ["results_shown", "results_sorted_by_price"],
              "actions": ["click('first_matching_product')"],
              "effects": ["item_selected", "view:detail"],
              "state_before": ["results_shown", "results_sorted_by_price", "view:collection"],
              "state_after": ["item_selected", "view:detail", "has_numeric_content"],
              "evidence": "Product detail heading, capacity options, price, and stock label are visible."
            },
            {
              "order": 4,
              "skill_id": "skill_read_visible_detail",
              "skill_name": "read_visible_detail",
              "semantic_goal": "Confirm capacity, price, and stock status before modifying the cart.",
              "preconditions": ["item_selected", "view:detail"],
              "actions": ["send_msg_to_user('Internal check: 1 TB option is visible and in stock at $79.99.')"],
              "effects": ["product_requirements_confirmed"],
              "state_before": ["item_selected", "view:detail"],
              "state_after": ["item_selected", "view:detail", "product_requirements_confirmed"],
              "evidence": "Visible labels include 1 TB, In stock, and $79.99."
            },
            {
              "order": 5,
              "skill_id": "skill_activate_named_control",
              "skill_name": "activate_named_control",
              "semantic_goal": "Select the 1 TB product option.",
              "preconditions": ["view:detail", "product_requirements_confirmed"],
              "actions": ["click('capacity_1tb')"],
              "effects": ["required_option_selected"],
              "state_before": ["view:detail", "product_requirements_confirmed"],
              "state_after": ["view:detail", "product_requirements_confirmed", "required_option_selected"],
              "evidence": "The 1 TB option has selected=true."
            },
            {
              "order": 6,
              "skill_id": "skill_activate_state_change_control",
              "skill_name": "activate_state_change_control",
              "semantic_goal": "Add one configured SSD to the cart.",
              "preconditions": ["item_selected", "required_option_selected"],
              "actions": ["fill('quantity', '1')", "click('add_to_cart')"],
              "effects": ["cart_nonempty", "item_in_cart"],
              "state_before": ["item_selected", "required_option_selected"],
              "state_after": ["item_selected", "required_option_selected", "cart_nonempty", "item_in_cart"],
              "evidence": "Success message says the SSD was added to the shopping cart."
            },
            {
              "order": 7,
              "skill_id": "skill_inspect_record_status",
              "skill_name": "inspect_record_status",
              "semantic_goal": "Open the cart and report quantity and subtotal.",
              "preconditions": ["cart_nonempty", "item_in_cart"],
              "actions": ["click('my_cart')", "send_msg_to_user('The selected 1 TB portable SSD is in the cart with quantity 1; subtotal is $79.99.')"],
              "effects": ["on_cart", "cart_summary_known"],
              "state_before": ["cart_nonempty", "item_in_cart"],
              "state_after": ["cart_nonempty", "item_in_cart", "on_cart", "cart_summary_known"],
              "evidence": "Cart row shows the selected item, quantity 1, and subtotal $79.99."
            }
          ],
          "final_state": {
            "url": "http://192.168.1.31:7770/checkout/cart/",
            "predicates": ["cart_nonempty", "item_in_cart", "on_cart", "cart_summary_known"]
          },
          "chain_validation": {
            "connected": true,
            "all_preconditions_supported": true,
            "skill_chain_length": 7,
            "contains_irreversible_action": false
          }
        }
        ```
        
- Vì đã xuất hiện task Semantic nên việc finetuning cho SLM sẽ tốt hơn nhiều
- Vì logic đã ổn nên đang tiến hành Craw dataset cho 3 Domain song song là (Shopping, Reddit và Wiki của webarena) và quá trình chạy có thể lâu vì đang call API để hỗ trợ tạo task Semantic khá nhiều
- Vấn đề râu ria đã được giải quyết:
    - Lí do tuần trước finetuning cho ra kết quả không tốt: Thought cho training data chưa tốt; Grounding yếu với combobox/select controls, BID thay đổi, repeated labels.